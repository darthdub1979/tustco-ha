#!/usr/bin/env python3
"""Offline sky events for Tustco Circadian.

No cloud, no packages, no runtime network. Everything is either calculated
(Meeus lunar phases, solar longitude, solar noon) or read from the bundled
eclipses.json catalog, which was downloaded ONCE during development.

Public entry point: sky_status(moment, config, sun_events=None)
"""

import json
import math
import os
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(BASE, "eclipses.json")

_EPOCH_JD = 2440587.5
_MEAN_NEW_MOON_JDE = 2451550.09765  # 2000-01-06 18:14 UT, Meeus ch. 49
_SYNODIC_DAYS = 29.530588853
_CATALOG_CACHE = None
_FULL_MOON_CACHE = {}
_SEASON_CACHE = {}


# ---------------------------------------------------------------------------
# Time / angle helpers
# ---------------------------------------------------------------------------

def julian_day(moment):
    """Julian Day (UT) from an aware datetime."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).timestamp() / 86400.0 + _EPOCH_JD


def jd_to_datetime(jd):
    seconds = (jd - _EPOCH_JD) * 86400.0
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def sin_deg(value):
    return math.sin(math.radians(value))


def norm360(value):
    return value % 360.0


# ---------------------------------------------------------------------------
# Full moons: Meeus Astronomical Algorithms ch. 49 (mean phase + main terms)
# ---------------------------------------------------------------------------

def _moon_terms(k):
    """Sun/moon anomalies and argument of latitude for lunation k."""
    t = k / 1236.85
    m = 2.5534 + 29.10535670 * k - 0.0000014 * t * t - 0.00000011 * t ** 3
    m1 = (201.5643 + 385.81693528 * k + 0.0107582 * t * t
          + 0.00001238 * t ** 3 - 0.000000058 * t ** 4)
    f = (160.7108 + 390.67050284 * k - 0.0016118 * t * t
         - 0.00000227 * t ** 3 + 0.000000011 * t ** 4)
    e = 1.0 - 0.002516 * t - 0.0000074 * t * t
    return m, m1, f, e


def full_moon_jde(k):
    """Approximate JDE of full moon number k, with Meeus' main corrections."""
    t = k / 1236.85
    # Meeus uses k + 0.5 for full moon; the T^2 term is the only noticeable
    # polynomial correction over the 2020-2050 span we care about.
    mean = (_MEAN_NEW_MOON_JDE + _SYNODIC_DAYS * (k + 0.5)
            + 0.0001337 * t * t - 0.000000150 * t ** 3
            + 0.00000000073 * t ** 4)
    m, m1, f, e = _moon_terms(k)
    correction = (
        -0.40614 * sin_deg(m1)
        + 0.17302 * e * sin_deg(m)
        + 0.01614 * sin_deg(2 * m1)
        + 0.01043 * sin_deg(2 * f)
        + 0.00734 * e * sin_deg(m1 - m)
        - 0.00715 * e * sin_deg(m1 + m)
        + 0.01086 * e * e * sin_deg(2 * m)
    )
    return mean + correction


def lunar_distance_km(moment):
    """Approximate Earth-Moon distance at an instant (Meeus ch. 45, main terms)."""
    jd = julian_day(moment)
    k = round((jd - _MEAN_NEW_MOON_JDE) / _SYNODIC_DAYS)
    m, m1, _f, _e = _moon_terms(k)
    elongation = m1 - m
    return (
        385000.56
        - 20905.355 * math.cos(math.radians(m1))
        - 3699.111 * math.cos(math.radians(2 * elongation - m1))
        - 2955.968 * math.cos(math.radians(2 * elongation))
        - 569.925 * math.cos(math.radians(2 * m1))
    )


def full_moons(year, offset_hours=0.0):
    """All full moons of a year as UTC datetimes, plus their local date.

    Results are cached per (year, offset) - the data never changes at runtime.
    """
    key = (year, offset_hours)
    if key in _FULL_MOON_CACHE:
        return _FULL_MOON_CACHE[key]

    start_jd = julian_day(datetime(year, 1, 1, tzinfo=timezone.utc)) - 2
    end_jd = julian_day(datetime(year + 1, 1, 1, tzinfo=timezone.utc)) + 2
    k_start = math.floor((start_jd - _MEAN_NEW_MOON_JDE) / _SYNODIC_DAYS) - 2
    k_end = math.ceil((end_jd - _MEAN_NEW_MOON_JDE) / _SYNODIC_DAYS) + 2

    local_tz = timezone(timedelta(hours=offset_hours))
    moons = []
    for k in range(k_start, k_end + 1):
        jde = full_moon_jde(k)
        # JDE ~ TT; Delta T in this era is about 69 seconds.
        utc = jd_to_datetime(jde - 69.0 / 86400.0)
        local_date = utc.astimezone(local_tz).date()
        if local_date.year == year:
            moons.append({
                "utc": utc,
                "local_date": local_date,
                "distance_km": lunar_distance_km(utc),
            })
    _FULL_MOON_CACHE[key] = moons
    return moons


def is_blue_moon(moment, offset_hours=0.0):
    """Second (or later) full moon in the same local calendar month."""
    local_tz = timezone(timedelta(hours=offset_hours))
    local = moment.astimezone(local_tz)
    moons = full_moons(local.year, offset_hours)
    same_month = [m for m in moons if m["local_date"].month == local.month]
    if len(same_month) < 2:
        return False, 0
    second = same_month[1]["local_date"]
    return local.date() == second, len(same_month)


def is_supermoon(moment, offset_hours=0.0, max_km=362000.0):
    """Full moon near perigee. Distance is approximate; threshold configurable."""
    local_tz = timezone(timedelta(hours=offset_hours))
    local = moment.astimezone(local_tz)
    for moon in full_moons(local.year, offset_hours):
        if moon["local_date"] == local.date():
            return moon["distance_km"] <= float(max_km), moon["distance_km"]
    return False, None


# ---------------------------------------------------------------------------
# Solar longitude -> solstices and equinoxes (Meeus ch. 25, low precision)
# ---------------------------------------------------------------------------

def solar_longitude(moment):
    jd = julian_day(moment)
    n = jd - 2451545.0
    mean_lon = norm360(280.460 + 0.9856474 * n)
    anomaly = norm360(357.528 + 0.9856003 * n)
    return norm360(mean_lon + 1.915 * sin_deg(anomaly) + 0.020 * sin_deg(2 * anomaly))


def season_events(year):
    """Approximate UTC instants of the four equinoxes/solstices."""
    if year in _SEASON_CACHE:
        return _SEASON_CACHE[year]

    targets = [
        (0.0, "equinox-march", datetime(year, 3, 20, tzinfo=timezone.utc)),
        (90.0, "solstice-june", datetime(year, 6, 21, tzinfo=timezone.utc)),
        (180.0, "equinox-september", datetime(year, 9, 22, tzinfo=timezone.utc)),
        (270.0, "solstice-december", datetime(year, 12, 21, tzinfo=timezone.utc)),
    ]
    found = []
    for target, label, approx in targets:
        start = approx - timedelta(days=3)
        lon0 = solar_longitude(start)
        target_unwrapped = target + 360.0 * round((lon0 - target) / 360.0)

        def signed_delta(offset_hours):
            lon = solar_longitude(start + timedelta(hours=offset_hours))
            lon += 360.0 * round((target_unwrapped - lon) / 360.0)
            return lon - target_unwrapped

        low, high = 0.0, 144.0
        if signed_delta(high) < 0:
            continue
        for _ in range(40):
            mid = (low + high) / 2.0
            if signed_delta(mid) < 0:
                low = mid
            else:
                high = mid
        instant = start + timedelta(hours=(low + high) / 2.0)
        found.append({"key": label, "utc": instant})
    _SEASON_CACHE[year] = found
    return found


def equation_of_time(moment):
    """NOAA simplified Equation of Time in minutes."""
    day = moment.timetuple().tm_yday
    gamma = 2 * math.pi / 365.0 * (day - 1)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )


def solar_noon_seconds(date, longitude, offset_hours):
    """Local seconds after midnight when the sun crosses the meridian."""
    noon = datetime(date.year, date.month, date.day, 12, tzinfo=timezone.utc)
    minutes = 720.0 - 4.0 * longitude - equation_of_time(noon) + 60.0 * offset_hours
    return minutes * 60.0


# ---------------------------------------------------------------------------
# Eclipse catalog (one-time download, bundled locally)
# ---------------------------------------------------------------------------

def catalog_path(config):
    """Resolve the configured catalog, allowing a filename relative to sky.py."""
    configured = str(config.get("sky_events", {}).get("catalog") or "")
    if not configured:
        return CATALOG_PATH
    if os.path.isabs(configured):
        return configured
    return os.path.join(BASE, configured)


def load_catalog(path=None):
    global _CATALOG_CACHE
    target = path or CATALOG_PATH
    if _CATALOG_CACHE is not None and path is None:
        return _CATALOG_CACHE
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = {"events": []}
    if path is None:
        _CATALOG_CACHE = data
    return data


def eclipse_on_date(moment, offset_hours, catalog=None):
    """Return the first eclipse whose UTC instant lands on this local date."""
    data = catalog if catalog is not None else load_catalog()
    local = moment.astimezone(timezone(timedelta(hours=offset_hours)))
    for event in data.get("events", []):
        try:
            utc = datetime.fromisoformat(str(event["utc"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if utc.astimezone(timezone(timedelta(hours=offset_hours))).date() != local.date():
            continue
        result = dict(event)
        result["local_time"] = utc.astimezone(timezone(timedelta(hours=offset_hours)))
        return result
    return None


def upcoming_events(config, offset_hours, moment=None, limit=5):
    """Human-readable next catalog events (solar eclipses filtered to Tucson)."""
    moment = moment or datetime.now()
    now_utc = moment.astimezone(timezone.utc)
    data = load_catalog(catalog_path(config))
    results = []
    for event in data.get("events", []):
        try:
            utc = datetime.fromisoformat(str(event["utc"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if utc <= now_utc:
            continue
        if (event.get("kind") == "solar"
                and config.get("sky_events", {}).get("solar_eclipse_local_only", True)
                and not event.get("local_relevant")):
            continue
        local = utc.astimezone(timezone(timedelta(hours=offset_hours)))
        results.append({
            "date": local.strftime("%Y-%m-%d"),
            "kind": event.get("kind"),
            "type": event.get("type"),
        })
    results.sort(key=lambda item: item["date"])
    return results[:limit]


# ---------------------------------------------------------------------------
# Combined status used by the scheduler
# ---------------------------------------------------------------------------

SKY_KEYS = (
    "solar-eclipse", "total-lunar-eclipse", "partial-lunar-eclipse",
    "penumbral-lunar-eclipse", "blue-moon", "supermoon",
    "solstice", "equinox",
)


def _key_for_eclipse(event):
    if event.get("kind") == "solar":
        return "solar-eclipse"
    kind = str(event.get("type", "")).lower()
    if "total" in kind:
        return "total-lunar-eclipse"
    if "partial" in kind:
        return "partial-lunar-eclipse"
    return "penumbral-lunar-eclipse"


def sky_status(moment, config, sun_events=None, force=None):
    """Describe any active sky event and the color/dimmer that should win.

    Priority: manual `force` > catalog eclipses > blue moon > supermoon >
    solstice/equinox. The ordinary full-moon accent is handled by circadian.py
    when no sky event is active.
    """
    sky_cfg = config.get("sky_events", {})
    result = {
        "enabled": bool(sky_cfg.get("enabled", False)),
        "event": None,
        "label": None,
        "reason": None,
        "color": None,
        "dimmer": None,
        "window": None,
        "next": [],
    }
    if not result["enabled"]:
        return result

    try:
        offset = float(sky_cfg.get("utc_offset_hours", -7.0))
    except (TypeError, ValueError):
        offset = -7.0
    local = moment.astimezone(timezone(timedelta(hours=offset)))
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    styles = sky_cfg.get("events", {})
    night_end = sky_cfg.get("night_end", "23:30")
    try:
        end_h, end_m = (int(part) for part in str(night_end).split(":"))
        night_end_seconds = end_h * 3600 + end_m * 60
    except (ValueError, TypeError):
        night_end_seconds = 23 * 3600 + 30 * 60

    def style(key):
        spec = styles.get(key, {})
        if not isinstance(spec, dict):
            spec = {}
        return str(spec.get("color", "FFFFFF")).upper(), int(spec.get("dimmer", 40))

    def night_window():
        if sun_events and "sunset" in sun_events:
            start = float(sun_events["sunset"]) + float(
                sky_cfg.get("sunset_offset_minutes", 60)) * 60.0
        else:
            start = 19 * 3600.0
        return start, night_end_seconds

    def in_night():
        start, end = night_window()
        return (seconds >= start or seconds <= end) if end < start else (start <= seconds <= end)

    def in_day_window():
        noon = solar_noon_seconds(local.date(), float(sky_cfg.get("longitude", -110.9747)), offset)
        half = float(sky_cfg.get("day_window_minutes", 180)) * 30.0
        return abs(seconds - noon) <= half

    candidates = {}

    eclipse = eclipse_on_date(local, offset, load_catalog(catalog_path(config)))
    if eclipse:
        key = _key_for_eclipse(eclipse)
        if sky_cfg.get("solar_eclipse_local_only", True) and key == "solar-eclipse" \
                and not eclipse.get("local_relevant"):
            eclipse = None
    if eclipse:
        key = _key_for_eclipse(eclipse)
        etime = eclipse["local_time"]
        eta = etime.hour * 3600 + etime.minute * 60 + etime.second
        if key == "solar-eclipse":
            half = float(sky_cfg.get("solar_window_minutes", 90)) * 60.0
            active = abs(seconds - eta) <= half
            window = "{} +/- {} min".format(
                etime.strftime("%H:%M"), int(float(sky_cfg.get("solar_window_minutes", 90))))
        else:
            active = in_night()
            start, end = night_window()
            window = "{} - {}".format(
                "{:02d}:{:02d}".format(int(start) // 3600, (int(start) % 3600) // 60),
                str(night_end))
        if active:
            label = str(eclipse.get("type", "Eclipse"))
            if eclipse.get("kind") == "solar":
                label = "{} solar eclipse".format(label)
            else:
                label = "{} lunar eclipse".format(label)
            candidates[key] = (label, "{} ({})".format(
                eclipse.get("date"), etime.strftime("%H:%M")), window)

    # Blue moon and supermoon only describe the full moon itself, so they
    # share the night window.
    blue, month_count = is_blue_moon(local, offset)
    if blue:
        start, _end = night_window()
        candidates["blue-moon"] = (
            "Blue moon", "second of {} full moons this month".format(month_count),
            "{} - {}".format(
                "{:02d}:{:02d}".format(int(start) // 3600, (int(start) % 3600) // 60),
                str(night_end)),
        )
    try:
        max_km = float(sky_cfg.get("supermoon_max_distance_km", 362000))
    except (TypeError, ValueError):
        max_km = 362000.0
    super_moon, distance = is_supermoon(local, offset, max_km)
    if super_moon:
        start, _end = night_window()
        candidates["supermoon"] = (
            "Supermoon", "full moon at ~{:.0f} km".format(distance or 0),
            "{} - {}".format(
                "{:02d}:{:02d}".format(int(start) // 3600, (int(start) % 3600) // 60),
                str(night_end)),
        )

    if in_day_window():
        for season in season_events(local.year):
            season_local = season["utc"].astimezone(timezone(timedelta(hours=offset)))
            if season_local.date() != local.date():
                continue
            key = season["key"]
            # Map "solstice-june"/"equinox-march" onto the two generic styles.
            style_key = "solstice" if key.startswith("solstice") else "equinox"
            candidates[style_key] = (
                key.replace("-", " ").title(),
                season_local.strftime("%H:%M") + " local",
                "+/- {} min of solar noon".format(
                    int(float(sky_cfg.get("day_window_minutes", 180)) / 2)),
            )

    result["next"] = upcoming_events(config, offset, moment)
    if force:
        key = str(force)
        if key not in SKY_KEYS:
            key = None
        candidates = {}
        if key:
            candidates[key] = ("Simulated " + key.replace("-", " "), "test override", "simulated")

    order = sky_cfg.get("priority", list(SKY_KEYS))
    for key in order:
        if key in candidates:
            label, reason, window = candidates[key]
            color, dimmer = style(key)
            result.update({
                "event": key,
                "label": label,
                "reason": reason,
                "color": color,
                "dimmer": dimmer,
                "window": window,
            })
            break
    return result
