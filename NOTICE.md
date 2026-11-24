# Third-party notices

Tustco Local Tools includes original code plus references to third-party
projects. We ship no third-party binaries in Git.

- **Home Assistant Core** (Apache-2.0) - platform we integrate with.
  <https://www.home-assistant.io/>
- **HACS** (MIT) - custom integration manager. Our local build patches HACS
  1.26.0 to work with GitHub's anonymous public API because we have no GitHub
  account; see `patches/HACS-1.26.0-anonymous.md`. Patched bundles are not
  included here.
- **Tasmota** (GPL-3.0) - the bulb firmware we derive from. Our additions are
  `xdrv_98_tustco.ino` and the build flags for separate single-purpose images.
  Any shipped modified firmware must keep its source available under GPL-3.0.
- **Raspberry Pi OS / Home Assistant OS** (various licenses) - base images used
  by the reference build script. Download from their official sources.
- **Eclipse Mosquitto** (EPL/EDL) - local MQTT broker used in the build.
- **Dropbear** (MIT) - local maintenance SSH inside the Pi image.

No ads, no analytics, no tracking, no phone-home code.
