# Tustco Presence — alpha1

Coarse RF motion tripwire using the two RGBW bulbs we already flashed.
**No reflash. No cloud. No account. No Home Assistant dependency.**

## What it does
Polls each bulb's reported Wi‑Fi signal over the LAN every 2 seconds, keeps a
~60-second rolling baseline, and fires an event when the signal drops by 5 dBm
or more for two samples in a row. A human body absorbs 2.4 GHz, so walking
between the router and a bulb shows up as a dip.

**It cannot identify what moved.** People, pets, fans, rain and appliances can
all move the signal. "Motion" means *something disturbed the RF near this bulb*.

## Files
- `presence.py` — watcher + small status web page
- `config.json` — bulbs, threshold, timings
- `state.json` — live readings (written by the daemon)
- `events.jsonl` — motion / clear event log

## Tuning (config.json)
| Key | Default | Meaning |
|---|---:|---|
| `poll_seconds` | 2 | How often to ask each bulb |
| `baseline_samples` | 30 | Rolling window (~60 s) |
| `drop_dbm` | 5 | Signal drop that counts as motion |
| `confirm_samples` | 2 | Consecutive drops before firing |
| `cooldown_seconds` | 30 | Minimum gap between events |
| `return_margin_dbm` | 3 | How close to baseline counts as clear |

To make it more sensitive: lower `drop_dbm` to 3–4 (more false alarms).
To make it calmer: raise it to 7–8 (may miss a quiet person).

## Run
On this PC, one reading:
```bash
cd /media/pdtust/AI/TustcoPresence && python3 presence.py --once
```

On the Pi it runs as a daemon. Status page: **http://192.168.1.221:8126/**
Raw state: **http://192.168.1.221:8126/state.json**

## Pi commands
```bash
ssh -i ~/.ssh/id_ed25519 root@192.168.1.221
# live state
cat /proc/1/root/config/tustco-presence/state.json
# recent events
tail -20 /proc/1/root/config/tustco-presence/events.jsonl
# restart
OLD=$(ps -ef | grep 'presence.py --daemon' | grep -v grep | awk '{print $2}'); [ -n "$OLD" ] && kill $OLD
TZ=America/Phoenix setsid /usr/sbin/chroot /proc/1/root /usr/local/bin/python3 -u /config/tustco-presence/presence.py --daemon </dev/null >> /proc/1/root/config/tustco-presence/presence.log 2>&1 &
```

## Honest limits
- Detects disturbance, not identity. Not a security camera.
- Only works while the bulb has power and is on `ViviNet`.
- Five milliseconds of magic: none. This is plain signal statistics on an
  always-on device we already own.
- Backyard version = another bulb outdoors, same code, different name in config.
- No reflash, no router changes, no extra SSIDs.

**End.**
