# Reference build scripts

These are the scripts used to produce the **native, no-Docker** Home Assistant
image for Raspberry Pi 1 (ARMv6) on Pedro's machine. They are provided as a
recipe, not as a one-command installer. Read them before running anything.

## What the build needs

The scripts expect this layout (edit the paths at the top of
`build-native-ha.sh` for your machine):

```
RaspberryPi/
  raspios-bullseye-armhf-lite.img   # official Raspberry Pi OS Lite (download yourself)
  hacs-1.26.0-patched/              # HACS 1.26.0 with the anonymous patch
  config-seed/core.config_entries   # discovered-device entries
  cast-pin.py                       # DashCast re-pin helper
  ../TustcoCircadian/               # this repo's apps/tustco-circadian
  ../TustcoPresence/                # this repo's apps/tustco-presence
  tustco-dashboard/                 # this repo's apps/tustco-dashboard
/tmp/opencode/hacore/               # extracted Alpine HA Core 2022.6.7 rootfs
/tmp/opencode/haos-rootfs-direct/   # glibc dropbear root from HA OS 6.6
```

A 6 GB SD card, root/sudo, loop devices and a Linux host are required.

## Safety notes

- No credentials are baked in. The image carries a **public** SSH key only.
- Run `renew-dashboard-token.sh` after flashing a fresh card.
- The image has no Docker, no Supervisor, no cloud dependency.
- `flash-ha-card-robust.sh` writes in chunks with retries; unsuspend any
  automounter that fights it (see README-NATIVE.md).

## Honest limits

- The finished image is ~6 GB, too large for a GitHub release asset. Publish
  the recipe here; host the image separately if bandwidth allows.
- Raspberry Pi 1 is slow. Startup takes minutes. That is expected.
