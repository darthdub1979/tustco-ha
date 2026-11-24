#!/bin/bash
# Create a fresh long-lived HA token for the Tustco Dashboard and install it
# on the Pi. Run this after flashing a fresh image (the token is a secret and
# is deliberately NOT stored on the build-drive image).
# Usage: ./renew-dashboard-token.sh [ha-host]
set -euo pipefail
HOST="${1:-192.168.1.221}"
KEY="$HOME/.ssh/id_ed25519"

read -rsp "Home Assistant password (user): " PASS; echo
TOKEN=$(python3 - "$HOST" "$PASS" <<'PY'
import json, sys, urllib.request, urllib.parse, websocket
host, password = sys.argv[1], sys.argv[2]
base = "http://%s:8123" % host
cid = base + "/"
def post(path, data):
    req = urllib.request.Request(base + path, data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())
flow = post("/auth/login_flow", {"client_id": cid, "handler": ["homeassistant", None], "redirect_uri": cid})
step = post("/auth/login_flow/" + flow["flow_id"], {"client_id": cid, "username": "user", "password": password})
payload = urllib.parse.urlencode({"grant_type": "authorization_code", "code": step["result"],
    "client_id": cid, "redirect_uri": cid}).encode()
login = json.loads(urllib.request.urlopen(urllib.request.Request(base + "/auth/token", data=payload,
    headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST"), timeout=30).read().decode())
tok = login["access_token"]
ws = websocket.create_connection(base.replace("http", "ws") + "/api/websocket", timeout=30)
json.loads(ws.recv())
ws.send(json.dumps({"type": "auth", "access_token": tok}))
json.loads(ws.recv())
ws.send(json.dumps({"id": 1, "type": "auth/long_lived_access_token",
                    "client_name": "Tustco Dashboard", "lifespan": 3650}))
while True:
    msg = json.loads(ws.recv())
    if msg.get("id") == 1:
        assert msg.get("success"), msg
        print(msg["result"])
        break
ws.close()
PY
)

printf '%s' "$TOKEN" | ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 -i "$KEY" "root@$HOST" \
  'cat > /proc/1/root/config/.storage/tustco_token && chmod 600 /proc/1/root/config/.storage/tustco_token && echo "token installed on Pi"'
