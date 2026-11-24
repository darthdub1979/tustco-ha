# Native Home Assistant on the original Raspberry Pi 1 — no Docker, no cloud

**Status (2026-11-24):** image built, flashed to the 32 GB card, card moved to the Pi 1 and
powered on. Home Assistant is live at `http://192.168.1.221:8123/` with page title
**Home Assistant**. SSH works. Owner account `user` created and verified through the HA
auth login flow; token exchange works and authenticated `GET /api/` returns
`{"message": "API running."}`. Ready for local devices.

## What this is

`/media/pdtust/AI/RaspberryPi/ha-native-pi1.img` (6.0 GB) boots the original 2011
Pi 1 (ARMv6) with:

- Raspbian Bullseye boot files + kernel/modules `6.1.21+`
- Extracted **Home Assistant Core 2022.6.7** Alpine ARMv6 runtime as `/`
- HA launched as a plain process: `/usr/local/bin/hass --config /config`
- **No Docker, no Supervisor, no containers, no cloud, no analytics, no Google TTS**
- Static IP `192.168.1.221/24`, gateway `192.168.1.1` — no DHCP dependency
- Local maintenance SSH (dropbear) on port 22 using the PC's existing `id_ed25519` key
- **Full local config restored 2026-11-24:** the original minimal config only had
  `frontend/http/api/config/onboarding/automation/script/scene`. `configuration.yaml` now
  explicitly enables the bundled offline-safe integrations: `recorder`, `history`,
  `logbook`, `sun`, `zone`, `system_health`, `map`, `media_source`, `usb`, `ssdp`,
  `zeroconf`, and the input helpers (`input_boolean/number/select/text/datetime`, `timer`,
  `counter`) plus Tucson coordinates. `default_config` was deliberately NOT used because it
  pulls in `cloud`/analytics. Backup: `/config/configuration.yaml.bak-before-full-config`.
  `hass --script check_config` passed; restart took ~2.5 min on the Pi 1. All components
  verified loaded via `GET /api/components`; discovery notification appeared.
- **HACS installed 2026-11-24 — anonymous mode, no GitHub account needed.** HACS 1.26.0
  copied to `/config/custom_components/hacs` and patched locally: empty YAML token is passed
  as `None` to both GitHub clients, and the "rate limit" check no longer disables HACS at
  GitHub's anonymous 60/hour limit (it fetches 6 repos per cycle instead). Config lives in
  `configuration.yaml` as `hacs:` with `token: ""`; no config flow or device code. HACS panel
  and `/hacsfiles/frontend/entrypoint.js` verified serving; `sensor.hacs` exists. Repo
  browsing needs the LAN's internet connection; HA itself still works with the WAN down.
  Patched bundle preserved at `hacs-1.26.0-patched/` and wired into `build-native-ha.sh`.
  GitHub request timeout raised 20 -> 45 s on the modern client only (the legacy client
  rejects that argument). Verified live: `hacs/info` has `disabled_reason: null`, 1071 repos
  via `hacs/repositories/list`, frontend JS HTTP 200. In YAML mode `sensor.hacs` starts
  `unknown` until an event, so an automation refreshes it 5 min after HA starts.
- **Device discovery completed 2026-11-24:** overnight HA created 8 discovery flows but left
  them waiting for a UI "Configure". All confirmable flows were accepted via the API. Live
  config entries: both TVs via `dlna_dmr`, Lenovo Smart Display 7 via `cast`, Brother printer
  via `brother` + `ipp`, and a persistent `samsungtv` entry for the curved 55" TV. Entities:
  `media_player.tv_samsung_6_series_55` (DLNA), `media_player.tv_samsung_4_series_32`,
  `media_player.living_room_display`, `media_player.samsung_6_series_55` (websocket control),
  plus four Brother printer sensors. The 32" TV's websocket needs a PIN accepted on the TV
  itself, so that flow was ignored; its DLNA entity gives working control instead. Wake-on-LAN
  helper `/usr/local/bin/wol-tv55.sh` is wired as `on_action` for the 55" TV's `turn_on`.
  Fresh-image reproducibility: `config-seed/core.config_entries` is copied into the image so
  discovered devices are already configured instead of sitting in a pending queue.
- **Tustco Dashboard built 2026-11-24** at `http://192.168.1.221:8124/`. Our own free-form dashboard,
  written from scratch in plain HTML/CSS/JS with a tiny Python stdlib server — no Docker, no HACS
  dependency, no CDN, no analytics, no account. The browser talks only to the local server on port
  8124; the server holds a long-lived HA token in `/config/.storage/tustco_token` (chmod 600) and
  proxies a strict allowlist of reads (`states`, `history/period`, `config`) plus three media-player
  services. The token never reaches the browser. Cards: state, media player with on/off, multi-entity
  history chart (normalized overlay = the "statistics graph" recipe), logical-device group, clock,
  text. Free-form drag/resize with 8 px snap, saved to `layout.json`; PHONE button gives a
  single-column fallback; LCARS button applies our own Star-Trek-inspired CSS skin built locally
  with system fonts (no Google Fonts, no card-mod). Starter layout has 10 cards wired to the real
  printers, TVs, Lenovo display, and HACS entity. Source: `tustco-dashboard/`; baked into
  `build-native-ha.sh`. Fresh images need `renew-dashboard-token.sh` (prompts for the HA password,
  creates a new long-lived token over SSH) because credentials are deliberately not stored on the
  exFAT build drive.
- **Loopback fix 2026-11-24:** the stripped rootfs booted with `lo` up but no `127.0.0.1` address,
  so processes on the Pi could not reach its own HA API. `ip link set lo up` and
  `ip addr add 127.0.0.1/8 dev lo` are now in the live `/etc/rc.local` and in the build script.
- **Bluetooth:** CSR USB dongle `0a12:0001` (BlueZ 5.58, `hci0` MAC `00:1A:7D:DA:71:03`).
  The `btusb` driver is loaded at boot, D-Bus + `bluetoothd --experimental` start from
  `/etc/rc.local`, and `hcitool lescan` sees nearby BLE devices. Note: HA Core 2022.6.7
  predates the unified `bluetooth` integration — use `bluetooth_tracker` /
  `bluetooth_le_tracker`, a custom component, or an MQTT bridge for BLE sensors.

`haos_rpi-6.6-direct.img` and `build-direct-core.sh` are superseded. Do not use them.

## Flash (requires the SD card in the PC reader)

The card is currently physically inside the Pi and the PC reader is empty.
Move the 32 GB card to the USB reader, then:

```bash
bash /media/pdtust/AI/RaspberryPi/flash-ha-card.sh
```

The script finds the removable ~32 GB card, asks for confirmation by printing the
target, flashes the 6 GB image, and verifies boot cmdline, `hass`, config, and SSH key.

Move the card back into the Pi and power it on.

## Verify

```bash
curl -i http://192.168.1.221:8123/          # expect Home Assistant onboarding/UI
ssh -i ~/.ssh/id_ed25519 root@192.168.1.221 # expect a shell
```

First boot takes a few minutes on the Pi 1. If SSH is up before the UI, that is fine.

**SSH gotchas discovered on live hardware:**
- Dropbear can take **~13 seconds** to send its banner on the Pi 1. Use
  `ssh -o ConnectTimeout=90 ...` — short timeouts look like a dead daemon.
- The SSH shell lands inside the bundled `/opt/sshroot` chroot, so `/config` and
  `/var/log` are not visible there. The real rootfs is reachable at `/proc/1/root`
  (e.g. `tail /proc/1/root/var/log/home-assistant.log`).
- The Pi 1 has no RTC and booted at 1970-01-01. Clock is now synced with
  `ntpd -n -q -p 192.168.1.1 -p pool.ntp.org`, added to `/etc/rc.local` on the card
  so it survives reboots.

## Recovery / maintenance

- Serial/keyboard console: root auto-logs in on `tty1` (`/bin/login -f root`).
- Boot logs: `/var/log/rc.local.log`
- HA logs: `/var/log/home-assistant.log`
- Edit config over SSH: `/config/configuration.yaml`, then `kill -HUP <hass pid>` or reboot.

## Rebuild

```bash
bash /media/pdtust/AI/RaspberryPi/build-native-ha.sh
```

Needs `/tmp/opencode/hacore` (extracted HA Core runtime) and
`/tmp/opencode/haos-rootfs-direct` (only for the bundled dropbear). Both are local
extracts of images pulled once on this PC; nothing is fetched at boot.

## Why native

Pedro's requirement: free, open source, offline, owned hardware — "what if everything
was destroyed and I had this computer and a Raspberry Pi and I'd have to rebuild
society?" Home Assistant is a Python program; Docker was only a packaging wrapper
and is not required to run it. This image has no runtime dependency on Docker,
Docker Hub, a cloud account, or a subscription.

## Lenovo Smart Display 7 (living room wall display)

- Dashboard: `http://192.168.1.221:8124/`. The display is pinned to
  `http://192.168.1.221:8124/?display=1` via DashCast (no root, no Google account).
  Cast app ID `84912283`; stock app is `E8C28D3C`.
- `cast-pin.py` runs on the Pi, checks once a minute, re-launches DashCast if
  somebody casts something else, and refreshes the page every 30 minutes. Both it
  and the dashboard are started with `setsid` in `/etc/rc.local` so an SSH
  disconnect cannot kill them.
- `?display=1` serves `layout-display.json` (10 cards, LCARS theme) and hides all
  editing chrome. The page POSTs its real viewport to `/viewport`; the Lenovo
  reports `1024x600`.
- **Voice boundary:** Chromium Cast disables `allow_user_media_access` by default,
  so a web page / DashCast receiver cannot use the microphone. "Hey Pedro" on this
  hardware requires rooting the Lenovo and installing our own Android kiosk app.
  REA findings and the pre-flash runbook are under
  `/media/pdtust/AI/LenovoSmartDisplay/`. No device has been unlocked or flashed.
