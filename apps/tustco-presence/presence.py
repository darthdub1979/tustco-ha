#!/usr/bin/env python3
"""Tustco Presence - coarse RF motion tripwire using existing Tasmota bulbs.

No reflash, no cloud, no account, no Home Assistant dependency.
Polls each bulb's reported Wi-Fi signal, keeps a rolling baseline, and fires
an event when the signal drops sharply (a body absorbing 2.4 GHz).

It cannot identify *what* moved. Wind, pets, rain and appliances can also
move the signal. Treat events as "something disturbed the RF near this bulb".
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("PRESENCE_CONFIG", os.path.join(BASE, "config.json"))
STATE_PATH = os.environ.get("PRESENCE_STATE", os.path.join(BASE, "state.json"))
EVENTS_PATH = os.environ.get("PRESENCE_EVENTS", os.path.join(BASE, "events.jsonl"))

_stop = threading.Event()
_lock = threading.Lock()
_devices = {}
_last_write = ""


def log(msg):
    print(datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + " " + msg, flush=True)


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    global _last_write
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    _last_write = path


def append_event(event):
    with open(EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")


def read_bulb(device, timeout):
    """Return (signal_dbm, rssi_percent, uptime_sec, power) or None."""
    url = "http://%s/cm?cmnd=Status%%200" % device["ip"]
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        sts = data.get("StatusSTS", {})
        wifi = sts.get("Wifi", {})
        signal = wifi.get("Signal")
        if signal is None:
            return None
        uptime = sts.get("UptimeSec")
        if uptime is None:
            uptime = data.get("StatusPRM", {}).get("UptimeSec")
        return {
            "signal": int(signal),
            "rssi": wifi.get("RSSI"),
            "uptime": uptime,
            "power": sts.get("POWER"),
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    except Exception as e:
        log("%s unreachable: %s" % (device.get("name", device.get("ip")), e))
        return None


class Tracker:
    def __init__(self, device, cfg):
        self.device = device
        self.name = device.get("name", device["ip"])
        self.window = int(cfg.get("baseline_samples", 30))
        self.threshold = float(cfg.get("drop_dbm", 5))
        self.confirm = int(cfg.get("confirm_samples", 2))
        self.cooldown = int(cfg.get("cooldown_seconds", 30))
        self.return_margin = float(cfg.get("return_margin_dbm", 3))
        self.samples = []
        self.baseline = None
        self.active_since = None
        self.last_event = 0.0
        self.drop_run = 0
        self.return_run = 0
        self.state = "idle"
        self.last_reading = None

    def sample(self, reading):
        self.last_reading = reading
        sig = reading["signal"]
        self.samples.append(sig)
        if len(self.samples) > self.window:
            self.samples.pop(0)
        if len(self.samples) < min(self.window, 10):
            return  # warm up

        self.baseline = statistics.median(self.samples)
        recent = statistics.median(self.samples[-self.confirm:]) if self.confirm > 1 else sig
        drop = self.baseline - recent
        now = time.time()

        if self.state == "idle":
            if drop >= self.threshold:
                self.drop_run += 1
            else:
                self.drop_run = 0
            if self.drop_run >= self.confirm and now - self.last_event >= self.cooldown:
                self.state = "motion"
                self.active_since = reading["time"]
                self._active_epoch = now
                self.last_event = now
                self.drop_run = 0
                ev = {
                    "type": "motion",
                    "device": self.name,
                    "ip": self.device["ip"],
                    "time": reading["time"],
                    "baseline_dbm": round(self.baseline, 1),
                    "signal_dbm": sig,
                    "drop_dbm": round(drop, 1),
                }
                append_event(ev)
                log("%s MOTION  baseline=%.1f now=%d drop=%.1f dBm" %
                    (self.name, self.baseline, sig, drop))
        else:
            if drop <= self.return_margin:
                self.return_run += 1
            else:
                self.return_run = 0
            if self.return_run >= self.confirm:
                self.state = "idle"
                self.return_run = 0
                dur = round(now - (self.active_since_epoch or now), 1)
                ev = {
                    "type": "clear",
                    "device": self.name,
                    "ip": self.device["ip"],
                    "time": reading["time"],
                    "duration_seconds": dur,
                }
                append_event(ev)
                log("%s CLEAR   after %ss" % (self.name, dur))

    @property
    def active_since_epoch(self):
        return getattr(self, "_active_epoch", None)

    def snapshot(self):
        return {
            "name": self.name,
            "ip": self.device["ip"],
            "signal_dbm": self.last_reading["signal"] if self.last_reading else None,
            "baseline_dbm": round(self.baseline, 1) if self.baseline is not None else None,
            "state": self.state,
            "samples": len(self.samples),
            "last": self.last_reading["time"] if self.last_reading else None,
        }


def watch(config):
    poll = float(config.get("poll_seconds", 2))
    timeout = float(config.get("http_timeout_seconds", 3))
    trackers = []
    for d in config.get("devices", []):
        t = Tracker(d, config)
        trackers.append(t)
        _devices[d["ip"]] = t
    log("Watching %d bulb(s), poll=%.1fs, drop>=%.1fdBm" %
        (len(trackers), poll, config.get("drop_dbm", 5)))

    while not _stop.is_set():
        for t in trackers:
            if _stop.is_set():
                break
            r = read_bulb(t.device, timeout)
            if r:
                t.sample(r)
            with _lock:
                save_json(STATE_PATH, {
                    "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "devices": [t.snapshot() for t in trackers],
                })
        _stop.wait(poll)


def serve(config, port):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    page = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tustco Presence</title><style>
body{background:#0b0f14;color:#d7e6f5;font:16px monospace;margin:2rem}
h1{color:#6cf;font-size:1.4rem}.row{padding:.6rem;border-left:6px solid #345;margin:.6rem 0;background:#121a24}
.motion{border-color:#f55;background:#2a1414}.idle{border-color:#3a6}
.small{color:#89a;font-size:.85rem}
</style></head><body><h1>TUSTCO PRESENCE</h1><div id="x">loading...</div>
<h2 style="font-size:1rem;color:#6cf;margin-top:1.5rem">Recent events</h2>
<div id="ev">none yet</div>
<script>async function u(){let d=await(await fetch('/state.json?t='+Date.now())).json();
document.getElementById('x').innerHTML=d.devices.map(o=>
`<div class="row ${o.state}"><b>${o.name}</b> — ${o.state.toUpperCase()}<br>
<span class="small">signal ${o.signal_dbm} dBm · baseline ${o.baseline_dbm} dBm · ${o.last||'waiting'}</span></div>`).join('');}
async function e(){let a=await(await fetch('/events.json?t='+Date.now())).json();
document.getElementById('ev').innerHTML=a.length?a.map(o=>
`<div class="small">${o.time||''} — <b>${String(o.type).toUpperCase()}</b> ${o.device||''} ${o.drop_dbm!=null?'drop '+o.drop_dbm+' dBm':(o.duration_seconds!=null?'after '+o.duration_seconds+'s':'')}</div>`).join(''):'none yet';}
u();e();setInterval(u,2000);setInterval(e,5000);</script></body></html>""".encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/state.json"):
                try:
                    with _lock:
                        with open(STATE_PATH, "rb") as f:
                            body = f.read()
                except Exception:
                    body = b'{"devices":[]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            elif self.path.startswith("/events.json"):
                try:
                    with _lock:
                        with open(EVENTS_PATH) as f:
                            lines = f.readlines()
                    items = [json.loads(x) for x in lines[-50:] if x.strip()]
                    items.reverse()
                    body = json.dumps(items).encode()
                except Exception:
                    body = b'[]'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            else:
                body = page
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    log("Status page http://*:%d/" % port)
    srv.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true", help="run watcher + status server forever")
    ap.add_argument("--once", action="store_true", help="take one reading from each bulb")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    config = load_json(CONFIG_PATH, {})
    if args.once:
        for d in config.get("devices", []):
            print(d.get("name", d["ip"]), json.dumps(read_bulb(d, 3)))
        return
    if not args.daemon:
        ap.print_help()
        return

    port = args.port or int(config.get("web_port", 8126))
    t = threading.Thread(target=watch, args=(config,), daemon=True)
    t.start()
    try:
        serve(config, port)
    except KeyboardInterrupt:
        _stop.set()


if __name__ == "__main__":
    main()
