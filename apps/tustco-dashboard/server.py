#!/usr/local/bin/python3
"""Tustco Dashboard - tiny local-only web server for the Raspberry Pi HA box.

No Docker, no cloud, no telemetry, no secrets in the browser. The browser talks
only to this process; this process talks to Home Assistant on 127.0.0.1 using a
long-lived token that never leaves the Pi.

Serves:
  GET  /                dashboard HTML/CSS/JS
  GET  /layout          saved card layout JSON
  POST /layout          save card layout JSON
  GET  /ha/<path>       read-only proxy to HA's REST API
  POST /ha/services/<allowed>  allowlisted service calls
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = "/config/.storage/tustco_token"
HA_BASE = "http://127.0.0.1:8123/api/"
PORT = 8124

# Read paths the browser may request. Everything else is refused.
READ_PREFIXES = (
    "states",
    "history/period",
    "config",
)
# Service calls the browser may make. Keep this list deliberately short.
WRITE_SERVICES = (
    "media_player/turn_on",
    "media_player/turn_off",
    "media_player/volume_set",
)

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/lcars.css": ("lcars.css", "text/css; charset=utf-8"),
}


def load_token():
    try:
        with open(TOKEN_FILE, "r") as fh:
            return fh.read().strip()
    except OSError as exc:
        print("cannot read HA token: %s" % exc, file=sys.stderr)
        return ""


def to_harequest(path, body=None):
    """Forward a request to HA with the server-side token."""
    token = load_token()
    if not token:
        raise RuntimeError("HA token missing on Pi")
    headers = {"Authorization": "Bearer " + token}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(HA_BASE + path, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read()
    if raw:
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            return raw.decode("utf-8", "ignore")
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "TustcoDash/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, obj, code=200):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_text(self, text, ctype="text/plain; charset=utf-8", code=200):
        raw = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if not length:
            return None
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in STATIC:
            fname, ctype = STATIC[path]
            try:
                with open(os.path.join(HERE, fname), "r", encoding="utf-8") as fh:
                    self.send_text(fh.read(), ctype)
            except OSError as exc:
                self.send_text("missing %s: %s" % (fname, exc), code=500)
            return

        if path == "/layout":
            # A wall display asks for ?display=1 and gets a layout sized to
            # its screen (no editing chrome, no off-screen cards).
            lname = "layout-display.json" if "display=1" in parsed.query else "layout.json"
            lfile = os.path.join(HERE, lname)
            try:
                with open(lfile, "r", encoding="utf-8") as fh:
                    self.send_json(json.load(fh))
            except (OSError, ValueError):
                self.send_json({"cards": []})
            return

        if path.startswith("/ha/"):
            target = path[4:] + (("?" + parsed.query) if parsed.query else "")
            if not target.startswith(READ_PREFIXES):
                self.send_json({"error": "read path not allowed"}, 403)
                return
            try:
                self.send_json(to_harequest(target))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 502)
            return

        self.send_text("not found", code=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/viewport":
            # Lets a wall display tell us its real screen size so we can build
            # a layout that fits it. No secrets, no device identity stored.
            body = self.read_body() or {}
            with open(os.path.join(HERE, "viewport.log"), "a", encoding="utf-8") as fh:
                fh.write("%s %sx%s dpr=%s %s\n" % (
                    self.address_string(), body.get("w"), body.get("h"),
                    body.get("dpr"), (body.get("ua") or "")[:160]))
            self.send_json({"ok": True})
            return

        if path == "/layout":
            body = self.read_body()
            if not isinstance(body, dict) or not isinstance(body.get("cards"), list):
                self.send_json({"error": "invalid layout"}, 400)
                return
            lfile = os.path.join(HERE, "layout.json")
            tmp = lfile + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(body, fh, indent=2)
            os.replace(tmp, lfile)
            self.send_json({"ok": True, "cards": len(body["cards"])})
            return

        if path.startswith("/ha/services/"):
            target = path[4:] + (("?" + parsed.query) if parsed.query else "")
            service = target.split("?", 1)[0].replace("services/", "", 1)
            if service not in WRITE_SERVICES:
                self.send_json({"error": "service not allowed"}, 403)
                return
            body = self.read_body() or {}
            try:
                self.send_json(to_harequest(target, body))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 502)
            return

        self.send_text("not found", code=404)


if __name__ == "__main__":
    os.chdir(HERE)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Tustco Dashboard listening on http://0.0.0.0:%d" % PORT, file=sys.stderr)
    srv.serve_forever()
