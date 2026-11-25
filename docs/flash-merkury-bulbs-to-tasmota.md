# Flashing an old Tuya Wi-Fi bulb to Tasmota (OTA, no soldering)

**What this covers:** the *first* hack — taking a cloud-only Tuya bulb and
getting local Tasmota firmware onto it over Wi-Fi, with no cloud account and no
opening the bulb.

**What this does NOT cover:** custom RGB firmware, circadian scheduling, motion
trips, or anything after the first flash. Those are separate projects.

> Only do this to hardware you own. Flashing a device you do not own, or
> interfering with someone else's network, is not okay. Mains-voltage bulbs are
> sealed — **do not open one**. If the OTA method fails, stop; do not improvise
> with a mains-powered device.

---

## 1. The bulbs this worked on

| | Bulb A | Bulb B |
|---|---|---|
| Model | Merkury `MI-BW210-999W` / `EBE-qpw35` | same |
| Chip | ESP8285 (Tensilica L106, 1 MB flash) | same |
| MAC | `24:62:ab:38:70:6d` | `2c:f4:32:cd:1b:81` |
| Result | `192.168.1.234`, `tasmota_38706D-4205` | `192.168.1.219`, `tasmota_CD1B81-7041` |

The original Tuya firmware was backed up before flashing:

| Backup | Size | SHA-256 |
|---|---|---|
| `firmware-38706d.bin` | 1,048,576 | `0169f9f5b2f239db684b42fe1bf0a28c5ee428293f07a498c01d3c34352cc49e` |
| `firmware-cd1b81.bin` | 1,048,576 | `0202529c91ef2a0923e102a948c0777965accc25162a13016a92ab71dd577ebd` |

**Check before you start:** confirm the exact model and chip first. Newer bulbs
often use different modules or newer Tuya firmware and this method may simply
not work on them. "New ones have it built in" is not something to assume in
either direction — verify the hardware, don't guess.

## 2. The tool

[`tuya-convert`](https://github.com/ct-Open-Source/tuya-convert) by ct-Open-Source
(GPL-3.0). It stands up a temporary AP called `vtrust-flash`, intercepts the
bulb's registration traffic, and delivers a replacement image over the air.

The version we used is preserved locally, including the patches below. Key
services started by `start_flash.sh`:

- `setup_ap.sh` — temporary AP + DNS redirect
- `fake-registration-server.py` — pretends to be Tuya's registration service
- `mosquitto` — local MQTT broker
- `psk-frontend.py` — TLS-PSK proxy (**patched**, see §3)
- `tuya-discovery.py` — UDP device discovery

The intermediate firmware serves the original flash back at
`http://10.42.42.42/backup` — **fetch and keep that backup before you flash
anything.**

## 3. The gotcha that actually mattered: binary PSK identity

Stock `tuya-convert` assumes the TLS PSK *identity* is UTF-8 text. These bulbs
send a **binary** identity whose first byte is `0x01` (the public "PSK Identity
02" work assumes `0x02`). The stock `sslpsk` binding tries to decode it as text
and dies, so the bulb never completes the handshake and the flash never starts.

The fix had two parts:

1. Use `sslpsk3` and patch its Python wrapper so the identity stays **raw
   bytes** end to end — both the client callback
   (`return identity, psk` without decoding) and the server callback
   (`return callback(identity or None)`).
2. Patch `scripts/psk-frontend.py` to import `sslpsk3 as sslpsk`, log the raw
   identity, and tolerate `str(e)` on modern Python SSL errors.

Do **not** "fix" this by rewriting the identity to `0x02`. That breaks it.
The original firmware dumps confirm these units use `0x01`.

<details>
<summary>Patch locations (reference)</summary>

- `sslpsk3/sslpsk3.py` — lines ~142–149 and ~159–169 in the installed wrapper:
  pass `identity` through as bytes, never `.decode()`.
- `tuya-convert/scripts/psk-frontend.py` — `import sslpsk3 as sslpsk`,
  `gen_psk_logged()` for raw-identity logging, and `str(e)` in the SSL error
  checks.

The exact identity bytes are device-specific and are deliberately **not**
published here. Only the leading `0x01` byte and the pattern matter.

</details>

## 4. Sequence

1. Put the bulb into its pairing/reset state (power cycle per the bulb's
   instructions) so it advertises its setup network.
2. Start `./start_flash.sh` on a Linux machine with a second Wi-Fi interface.
3. Join `vtrust-flash` with a phone and let the app/registration flow run.
   Watch `smarthack-psk.log` — with the patch you should see
   `RAW IDENTITY ... len=...` beginning `01`, then a `PSK:` line.
4. The intermediate firmware installs. Wait for it to request `10.42.42.42`.
5. **Fetch the backup** from the intermediate firmware before proceeding:
   `curl -JOm 90 http://10.42.42.42/backup`
6. Use `./firmware_picker.sh` and choose a Tasmota image that fits the OTA
   slot (~512 KB on a 1 MB part). Our 600,960-byte full build does **not** fit;
   use a small/lite build.
7. Clean up completely afterwards: stop the temporary AP, DNS redirects and
   the `10.42.42.0/24` route, and restore your router config.

## 5. Honest limitations

- The small Tasmota image that fits has the **SM16716 RGB driver stripped
  out** — you get local control, but not full color out of the box. Getting
  RGB back required a separate custom build and is out of scope for this guide.
- This is OTA only. No serial adapter, no soldering, no opening the bulb.
- If the handshake doesn't happen, do not force it. Different bulb generations
  genuinely need different approaches.
- Your network changes during the flash. Back up the router config first, as
  we did (`router-backup/`), and restore it after.

## 6. License / provenance

`tuya-convert` is GPL-3.0 and Tasmota is GPL-3.0 — credit them, and if you
distribute a modified binary, keep its source available. This guide and the
non-GPL parts of this repo are MIT (see `LICENSE`). We wrote this from our own
flash logs and backups, not by copying anyone's documentation wholesale.

**Follow the recipe, don't clone the cookbook.**
