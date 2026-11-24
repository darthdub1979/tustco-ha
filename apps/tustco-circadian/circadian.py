#!/usr/bin/env python3
"""Tustco Circadian alpha3 - local adaptive lighting scheduler.

No cloud, no account, no dependencies. Talks to Tasmota bulbs over LAN.

alpha2: real offline sunrise/sunset; full-moon blue accent.
alpha3: sky events from a bundled eclipse calendar plus offline blue moon,
        supermoon and solstice/equinox calculations (see sky.py).
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from math import acos, cos, degrees, pi, radians, sin, tan

try:
    import sky
except ImportError:  # an older Pi copy without sky.py still runs the daily rhythm
    sky = None

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
STATE_PATH = os.path.join(BASE, "state.json")

MOON_REF = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
SYNODIC_MONTH_DAYS = 29.530588853


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as exc:
        print("WARN: could not read {}: {}".format(path, exc), file=sys.stderr)
        return default


def parse_hhmm(value):
    hour, minute = str(value).split(":")
    total = int(hour) * 3600 + int(minute) * 60
    if total < 0 or total > 86400:
        raise ValueError("invalid time: {}".format(value))
    return total


def fmt_seconds(seconds):
    seconds = int(seconds) % 86400
    return "{:02d}:{:02d}".format(seconds // 3600, (seconds % 3600) // 60)


def seconds_of(moment):
    return moment.hour * 3600 + moment.minute * 60 + moment.second


def hex_to_rgb(value):
    value = str(value).strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("color must be 6 hex digits: {}".format(value))
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "".join("{:02X}".format(int(round(channel))) for channel in rgb)


def lerp(start, end, fraction):
    return start + (end - start) * fraction


def utc_offset_hours(moment):
    offset = moment.astimezone().utcoffset()
    return 0.0 if offset is None else offset.total_seconds() / 3600.0


def solar_event_seconds(date, latitude, longitude, offset_hours, rising):
    """NOAA simplified solar rise/set. Returns local seconds after midnight."""
    day_of_year = date.timetuple().tm_yday
    gamma = 2 * pi / 365 * (day_of_year - 1 + (12 - 12) / 24.0)

    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * cos(gamma)
        - 0.032077 * sin(gamma)
        - 0.014615 * cos(2 * gamma)
        - 0.040849 * sin(2 * gamma)
    )

    declination = (
        0.006918
        - 0.399912 * cos(gamma)
        + 0.070257 * sin(gamma)
        - 0.006758 * cos(2 * gamma)
        + 0.000907 * sin(2 * gamma)
        - 0.002697 * cos(3 * gamma)
        + 0.00148 * sin(3 * gamma)
    )

    lat = radians(latitude)
    zenith = radians(90.833)
    value = cos(zenith) / (cos(lat) * cos(declination)) - tan(lat) * tan(declination)
    value = max(-1.0, min(1.0, value))
    hour_angle = degrees(acos(value))

    longitude_term = longitude + hour_angle if rising else longitude - hour_angle
    utc_minutes = 720 - 4 * longitude_term - equation_of_time
    local_minutes = utc_minutes + 60 * offset_hours
    return local_minutes * 60


def sun_events(moment, config):
    events_cfg = config.get("sun_events", {})
    if not events_cfg.get("enabled", False):
        return None
    try:
        latitude = float(events_cfg.get("latitude", 32.2226))
        longitude = float(events_cfg.get("longitude", -110.9747))
    except (TypeError, ValueError):
        return None

    offset = events_cfg.get("utc_offset_hours")
    offset = float(offset) if offset is not None else utc_offset_hours(moment)

    try:
        sunrise = solar_event_seconds(moment.date(), latitude, longitude, offset, True)
        sunset = solar_event_seconds(moment.date(), latitude, longitude, offset, False)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None

    return {
        "sunrise": sunrise,
        "sunset": sunset,
        "sunrise_text": fmt_seconds(sunrise),
        "sunset_text": fmt_seconds(sunset),
        "offset_hours": offset,
    }


def moon_phase(moment):
    if moment.tzinfo is None:
        moment = moment.astimezone(timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)
    elapsed_days = (moment - MOON_REF).total_seconds() / 86400.0
    fraction = (elapsed_days / SYNODIC_MONTH_DAYS) % 1.0
    illumination = (1.0 - cos(2 * pi * fraction)) * 50.0
    return fraction, illumination


def moon_window(moment, config, events=None):
    moon_cfg = config.get("moon", {})
    info = {
        "enabled": bool(moon_cfg.get("enabled", False)),
        "active": False,
        "phase": None,
        "illumination": None,
        "window": None,
    }
    if not info["enabled"]:
        return info

    fraction, illumination = moon_phase(moment)
    info["phase"] = round(fraction, 4)
    info["illumination"] = round(illumination, 1)

    if illumination < float(moon_cfg.get("min_illumination", 90)):
        return info

    if events and "sunset" in events:
        start = events["sunset"] + int(moon_cfg.get("start_offset_minutes", 60)) * 60
    else:
        start = parse_hhmm(moon_cfg.get("start", "19:00"))

    end = parse_hhmm(moon_cfg.get("end", "23:30"))
    seconds = seconds_of(moment)
    info["window"] = "{} - {}".format(fmt_seconds(start), fmt_seconds(end))
    info["active"] = (seconds >= start or seconds <= end) if end < start else (start <= seconds <= end)
    return info


def sky_for(moment, config, events=None, force=None):
    if sky is None:
        return {"enabled": False, "event": None, "label": None, "reason": None}
    return sky.sky_status(moment, config, events, force=force)


def build_keyframes(moment, config, events=None):
    base = config.get("keyframes", [])
    if not base:
        raise ValueError("config has no keyframes")

    night_start = hex_to_rgb(base[0]["color"])
    night_dim = int(base[0]["dimmer"])
    night_end = hex_to_rgb(base[-1]["color"])
    night_end_dim = int(base[-1]["dimmer"])

    if not events:
        return sorted(
            [(parse_hhmm(frame["time"]), hex_to_rgb(frame["color"]), int(frame["dimmer"])) for frame in base],
            key=lambda item: item[0],
        )

    events_cfg = config.get("sun_events", {})
    sunrise = events["sunrise"]
    sunset = events["sunset"]

    def point(seconds, spec, fallback_rgb, fallback_dim):
        seconds = max(0, min(86400, float(seconds)))
        return seconds, hex_to_rgb(spec.get("color", rgb_to_hex(fallback_rgb))), int(spec.get("dimmer", fallback_dim))

    points = [
        (0, night_start, night_dim),
        point(
            sunrise - float(events_cfg.get("pre_sunrise_minutes", 30)) * 60,
            events_cfg.get("pre_sunrise", {}),
            night_start,
            night_dim,
        ),
        point(sunrise, events_cfg.get("sunrise", {}), night_start, night_dim),
        point(
            sunrise + float(events_cfg.get("post_sunrise_minutes", 90)) * 60,
            events_cfg.get("morning", {}),
            (255, 242, 213),
            85,
        ),
        point(
            sunset - float(events_cfg.get("pre_sunset_minutes", 60)) * 60,
            events_cfg.get("golden_hour", {}),
            (255, 242, 213),
            80,
        ),
        point(sunset, events_cfg.get("sunset", {}), (255, 209, 160), 55),
        point(
            sunset + float(events_cfg.get("post_sunset_minutes", 60)) * 60,
            events_cfg.get("after_sunset", {}),
            night_start,
            night_dim,
        ),
        (86400, night_end, night_end_dim),
    ]
    return sorted(points, key=lambda item: item[0])


def schedule_at(moment, config, events=None):
    points = build_keyframes(moment, config, events)
    seconds = seconds_of(moment)

    if seconds <= points[0][0]:
        return rgb_to_hex(points[0][1]), points[0][2]

    for index in range(len(points) - 1):
        t0, rgb0, dim0 = points[index]
        t1, rgb1, dim1 = points[index + 1]
        if t0 <= seconds <= t1:
            fraction = 0.0 if t1 == t0 else (seconds - t0) / float(t1 - t0)
            rgb = tuple(lerp(rgb0[i], rgb1[i], fraction) for i in range(3))
            dim = int(round(lerp(dim0, dim1, fraction)))
            return rgb_to_hex(rgb), max(1, min(100, dim))

    return rgb_to_hex(points[-1][1]), points[-1][2]


def send_command(ip, command, timeout=6, retries=2):
    url = "http://{}/cm?cmnd={}".format(ip, urllib.parse.quote(str(command)))
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace").strip()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(0.5)
    raise RuntimeError("{}: {}".format(type(last_error).__name__, last_error))


def apply_once(moment, config, state, dry_run=False, force=False, cache=None,
               simulate_sky=None):
    if state.get("paused"):
        print("{} PAUSED - no changes sent".format(moment.isoformat(timespec="seconds")))
        return None

    events = sun_events(moment, config)
    moon = moon_window(moment, config, events)
    current_sky = sky_for(moment, config, events, force=simulate_sky)

    override = state.get("override")
    if override:
        color = str(override["color"]).upper()
        dimmer = int(override["dimmer"])
        source = "override"
    else:
        color, dimmer = schedule_at(moment, config, events)
        source = "schedule"
        if current_sky.get("event"):
            color = str(current_sky["color"]).upper()
            dimmer = int(current_sky["dimmer"])
            source = "sky:{}".format(current_sky["event"])
        elif moon["active"]:
            moon_cfg = config.get("moon", {})
            color = str(moon_cfg.get("color", "6E8CFF")).upper()
            dimmer = int(moon_cfg.get("dimmer", 25))
            source = "full-moon"

    color_command = "Color {}00".format(color)
    dimmer_command = "Dimmer {}".format(dimmer)
    signature = (color, dimmer)

    if cache is not None and not force and cache.get("signature") == signature:
        return None

    for ip in config["devices"]:
        if dry_run:
            print("{} DRY {} -> {} ; {}".format(
                moment.isoformat(timespec="seconds"), ip, color_command, dimmer_command))
            continue
        try:
            send_command(ip, color_command)
            send_command(ip, dimmer_command)
            detail = ""
            if source.startswith("sky:"):
                detail = " {} ({})".format(
                    current_sky.get("label"), current_sky.get("reason"))
            elif source == "full-moon":
                detail = " moon={}%".format(moon["illumination"])
            print("{} {} [{}]{} -> {} / {}%".format(
                moment.isoformat(timespec="seconds"), ip, source, detail, color, dimmer))
        except RuntimeError as exc:
            print("{} {} ERROR {}".format(
                moment.isoformat(timespec="seconds"), ip, exc), file=sys.stderr)

    if cache is not None:
        cache["signature"] = signature
    return signature


def run_demo(seconds, config, state, dry_run=False, simulate_sky=None):
    base = datetime.combine(datetime.now().date(), datetime.now().time().replace(
        hour=0, minute=0, second=0, microsecond=0))
    steps = max(4, int(seconds))
    delay = seconds / float(steps)
    print("Tustco Circadian demo: 24 hours compressed into {}s".format(seconds))
    if config.get("sun_events", {}).get("enabled"):
        events = sun_events(base, config)
        if events:
            print("Sun today: sunrise {} / sunset {}".format(
                events["sunrise_text"], events["sunset_text"]))
    moon = moon_window(base, config, sun_events(base, config))
    print("Moon now: {}% illuminated, active={}, window={}".format(
        moon["illumination"], moon["active"], moon["window"]))
    current_sky = sky_for(base, config, sun_events(base, config), force=simulate_sky)
    if current_sky.get("event"):
        print("Sky event: {} - {} ({})".format(
            current_sky["label"], current_sky.get("reason"), current_sky.get("window")))
    else:
        print("Sky event: none today")

    cache = {"signature": None}
    for step in range(steps + 1):
        fraction = step / float(steps)
        moment = base + timedelta(seconds=fraction * 86400)
        apply_once(moment, config, state, dry_run=dry_run, force=True, cache=cache,
                   simulate_sky=simulate_sky)
        if step < steps:
            time.sleep(delay)
    print("Demo complete. Returning to real current time.")
    apply_once(datetime.now(), config, load_json(STATE_PATH, {}),
               dry_run=dry_run, force=True)


def run_daemon(config, interval, dry_run=False):
    print("Tustco Circadian daemon started. Interval: {}s".format(interval))
    now = datetime.now()
    events = sun_events(now, config)
    if events:
        print("Sun today: sunrise {} / sunset {}".format(
            events["sunrise_text"], events["sunset_text"]))
    moon = moon_window(now, config, events)
    print("Moon: {}% illuminated, active={}, window={}".format(
        moon["illumination"], moon["active"], moon["window"]))
    current_sky = sky_for(now, config, events)
    if current_sky.get("event"):
        print("Sky event: {} - {}".format(current_sky["label"], current_sky.get("reason")))

    cache = {"signature": None}
    while True:
        now = datetime.now()
        apply_once(now, config, load_json(STATE_PATH, {}),
                   dry_run=dry_run, cache=cache)
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="apply current target once")
    group.add_argument("--daemon", action="store_true", help="run forever")
    group.add_argument("--demo", metavar="SECONDS", type=float,
                       help="run an accelerated 24-hour demo")
    parser.add_argument("--dry-run", action="store_true", help="print commands only")
    parser.add_argument("--simulate-sky", metavar="EVENT",
                        help="test a sky event now without waiting for the real date")
    args = parser.parse_args()

    config = load_json(CONFIG_PATH, {})
    if not config.get("devices") or not config.get("keyframes"):
        print("ERROR: invalid config: {}".format(CONFIG_PATH), file=sys.stderr)
        return 2

    state = load_json(STATE_PATH, {"paused": False, "override": None})

    if args.demo is not None:
        run_demo(args.demo, config, state, dry_run=args.dry_run,
                 simulate_sky=args.simulate_sky)
    elif args.daemon:
        run_daemon(config, int(config.get("interval_seconds", 60)),
                   dry_run=args.dry_run)
    else:
        apply_once(datetime.now(), config, state, dry_run=args.dry_run, force=True,
                   simulate_sky=args.simulate_sky)
    return 0


if __name__ == "__main__":
    sys.exit(main())
