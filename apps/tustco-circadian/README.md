# Tustco Circadian — alpha3

**Status:** alpha3, built 2026-11-24  
**Owner:** Tustco Industries  
**Built by:** Black Box (General)  
**Runs on:** always-on Raspberry Pi 1 (`192.168.1.221`), with a copy on this PC for development  
**Purpose:** local, offline adaptive lighting for the two Merkury RGBW bulbs.

---

## What it is

Tustco Circadian is a small Python scheduler that sends `Color` and `Dimmer` commands to our Tasmota bulbs over the LAN. It is **not** a cloud service, account, subscription, Docker, or Home Assistant dependency.

The bulbs run our own `9.2.0(tustco-rgb)` firmware with the SM16716 driver re-enabled and Jade's verified pin map. See `/media/pdtust/AI/TuyaFlash/firmware/README-TUSTCO-SM16716.md`.

### Version history

- **alpha1** — silence-based editing? No: first lighting scheduler with fixed clock keyframes.
- **alpha2** — real offline sunrise/sunset from Tucson coordinates; full-moon blue accent.
- **alpha3** — sky events: bundled eclipse calendar + offline blue moon, supermoon, solstice/equinox, solar noon.

### Honest limits

- One white channel, not separate warm/cool LEDs. Color temperature is **emulated by mixing RGB**.
- Sunrise/sunset, lunar phase, and solstice math are simplified offline calculations — close enough for a lighting rhythm, not an observatory.
- Eclipse times come from a **one-time download** of NASA/Fred Espenak predictions (via Wikipedia), cached in `eclipses.json`. The Pi never touches the internet for this.
- A real eclipse or blue moon is a **rare-event flourish**, not a daily effect. Use `--simulate-sky` to test without waiting years.
- The wall switch stays authoritative for on/off. The daemon only sends `Color` and `Dimmer`; bulbs use `PowerOnState 3`.

---

## Files

- `config.json` — devices, sun/moon settings, sky-event styles/priorities, presets
- `circadian.py` — scheduler/daemon
- `sky.py` — offline sky-event engine (no packages, no network)
- `eclipses.json` — 140 solar/lunar eclipse events, 2020–2050, bundled locally
- `circadianctl.py` — status/pause/resume/clear/preset control
- `demo.sh` — saved compressed demo command (`circadian-demo`)
- `state.json` — pause/override state on the Pi
- `README.md` — this file

---

## Sun-driven schedule

| Event | Offset from sun | Color | Dimmer | Feel |
|---|---:|---|---:|---|
| Pre-sunrise | -30 min | `FF8C3A` | 25% | amber before dawn |
| Sunrise | 0 | `FFD1A0` | 55% | warm golden dawn |
| Morning | +90 min | `FFF2D5` | 85% | crisp / clean |
| Golden hour | -60 min before sunset | `FFF2D5` | 80% | warm afternoon |
| Sunset | 0 | `FFD1A0` | 55% | visible orange transition |
| After sunset | +60 min | `FF8C3A` | 30% | night wind-down |
| Overnight | -- | `FF8C3A` | 20% | candlelight amber |

Computed for Tucson today: **sunrise 07:00**, **sunset 17:20** MST.

## Moon and sky events

Priority: **manual preset override → sky event → full-moon blue → schedule**.

| Event | When | Color | Dimmer |
|---|---|---|---:|
| Solar eclipse | catalog time +/- 90 min, Tucson-relevant only | `FF5A1F` | 15 |
| Total lunar eclipse (red moon) | sunset + 60 min → 23:30 | `A31515` | 30 |
| Partial lunar eclipse | same night window | `B84A2A` | 30 |
| Penumbral lunar eclipse | same night window | `C98A5A` | 35 |
| Blue moon (2nd full moon of month) | same night window | `3B5BFF` | 22 |
| Supermoon (full moon ≈ ≤362,000 km) | same night window | `FFF0C4` | 40 |
| Solstice | +/- 90 min of solar noon | `FFC36B` | 65 |
| Equinox | +/- 90 min of solar noon | `E8F0FF` | 55 |
| Ordinary full moon (≥90% illuminated) | sunset + 60 min → 23:30 | `6E8CFF` | 25 |

Real examples in the bundled data: **2026-05-31 is both a blue moon and a supermoon** (blue moon wins by priority); **2026-08-27 evening** has a partial lunar eclipse visible from Tucson.

---

## Presets

`circadianctl.py preset <name>` holds a manual override until cleared:

```text
candle  warm  crisp  daylight
jade    teal  cardinal white
moon    eclipse  blood-moon  blue-moon  supermoon
```

---

## Commands

Development copy:

```bash
cd /media/pdtust/AI/TustcoCircadian
python3 circadianctl.py status
python3 circadian.py --once --dry-run
python3 circadian.py --demo 60 --dry-run
python3 circadian.py --once --simulate-sky total-lunar-eclipse --dry-run
```

Saved demo (pauses the Pi daemon, runs 24 hours in 75 seconds, resumes):

```bash
circadian-demo
# or
bash /media/pdtust/AI/TustcoCircadian/demo.sh 90
```

On the Pi:

```bash
/usr/sbin/chroot /proc/1/root /usr/local/bin/python3 \
  /config/tustco-circadian/circadianctl.py status
```

---

## Deployment

alpha3 is deployed to `/config/tustco-circadian/` on the Pi and its daemon is running. `rc.local` starts it on boot, and `/media/pdtust/AI/RaspberryPi/build-native-ha.sh` copies it into fresh images.

The Pi needs only LAN access to the bulbs. NTP time sync is the only internet-adjacent dependency, and even that is optional for the rhythm itself.

---

## Boundaries

- No cloud, account, subscription, telemetry, or Docker.
- No router, VLAN, or SSID changes.
- No reflashing from this project (the firmware work lives in `/media/pdtust/AI/TuyaFlash/`).
- Pedro visually verifies colors; Black Box has no camera/vision in this session.
- "Follow the recipe, don't clone the cookbook": our own local implementation of Pedro's lighting cheat sheet and his eclipse/sky-event request.

**End.**
