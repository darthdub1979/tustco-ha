# Tustco Local Tools for Home Assistant

Local-first tools for people who own their hardware. No cloud, no account, no
subscription, no telemetry. Everything talks over your LAN.

This repository is the **code and documentation**. Binary SD images and
firmware builds are intentionally not stored in Git.

## What's in it

- `custom_components/tustco/` - a small Home Assistant integration:
  - `sensor.tustco_presence` - reads Tustco Presence (`/state.json`) and reports
    `idle`, `motion`, `unknown`, or `unavailable`.
  - `tustco.alert` service - sends a color pulse to a bulb running our
    `tustco-alert` firmware, then restores the bulb's previous color.
- `apps/` - the offline Python tools used on the Pi:
  - `tustco-presence/` - RF tripwire using bulb Wi-Fi signal changes.
  - `tustco-circadian/` - offline sunrise/sunset/moon schedule and color curve.
  - `tustco-dashboard/` - our own free-form local dashboard (no CDN, no account).
- `tools/` - the reference Raspberry Pi 1 native HA image build scripts and
  notes. These are **not turnkey**; see `tools/README.md` for prerequisites.
- `patches/` - how we run HACS 1.26.0 without a GitHub account.

## Install via HACS (after the GitHub repo exists)

1. In HA: **Settings > Devices & Services > HACS > Custom repositories**.
2. Add `https://github.com/darthdub1979/tustco-ha` as an **Integration**.
3. Search for **Tustco Local Tools** and install it.
4. Restart Home Assistant.
5. Enable it in `configuration.yaml` (below).

Manual install: copy `custom_components/tustco/` into your HA config's
`custom_components/` directory and restart.

## Configuration

```yaml
tustco:
  bulb_host: 192.168.1.219       # bulb running tustco-alert firmware
  presence_host: 192.168.1.221   # Pi running Tustco Presence

sensor:
  - platform: tustco
    host: 192.168.1.221
```

Example automation / developer-tools service call:

```yaml
service: tustco.alert
data:
  host: 192.168.1.219
  color: "FF0000"   # red alert
  count: 3
```

Color language (work in progress): red = alert, yellow = caution,
flashing white = "wand" sparkle, distinct patterns for yes / no /
"this happened". The firmware proves one ability at a time before we
combine them into the message beacon.

## Compatibility

Built and tested on **Home Assistant Core 2022.6.7** (Python 3.10, Pi 1 ARMv6).
Newer HA versions may work but are not tested here.

## Boundaries

- **Our original code** is MIT licensed (see `LICENSE`).
- **Tasmota-derived bulb firmware is GPL-3.0** and is not included here. If we
  ship a modified Tasmota image, its source must remain available.
- HACS and Tasmota are third-party projects; this repo is not affiliated with
  them. "Follow the recipe but don't clone the cookbook" - we learn from
  projects and write our own code.
- No credentials, tokens, passwords, or private keys belong in this repo.
  The reference build bundles only a **public** SSH key.

## Status

Alpha. Built by Tustco Industries for Tustco Industries, then shared.
