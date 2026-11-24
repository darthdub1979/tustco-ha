#!/bin/bash
# Build a NATIVE Home Assistant SD image for Raspberry Pi 1 (ARMv6).
# No Docker, no Supervisor, no cloud. HA Core 2022.6.7 runs as a plain process.
set -euo pipefail

DIR=/media/pdtust/AI/RaspberryPi
BASE=$DIR/raspios-bullseye-armhf-lite.img
OUT=$DIR/ha-native-pi1.img
HACORE=/tmp/opencode/hacore
SSHROOT=/tmp/opencode/haos-rootfs-direct
HACSBUNDLE=$DIR/hacs-1.26.0-patched
CONFIGSEED=$DIR/config-seed/core.config_entries
WOLSCRIPT=$DIR/wol-tv55.sh
DASHDIR=$DIR/tustco-dashboard
CIRCADIR=$DIR/../TustcoCircadian
PRESENCEDIR=$DIR/../TustcoPresence
RASPSRC=/mnt/rasp-src
IMG_SIZE=6G
LOOP=""
RSRC_LOOP=""

cleanup() {
  [ -n "$LOOP" ] && sudo losetup -d "$LOOP" 2>/dev/null || true
  [ -n "$RSRC_LOOP" ] && sudo losetup -d "$RSRC_LOOP" 2>/dev/null || true
  sudo umount /mnt/native-root /mnt/native-boot "$RASPSRC" 2>/dev/null || true
}
trap cleanup EXIT

# Never copy live /proc or /sys into the image.
sudo bash -c '
for i in $(seq 1 12); do
  umount /tmp/opencode/hacore/proc 2>/dev/null || break
done
for i in $(seq 1 12); do
  umount /tmp/opencode/hacore/sys 2>/dev/null || break
done
for m in /tmp/opencode/haos-rootfs-direct/dev/pts /tmp/opencode/haos-rootfs-direct/proc /tmp/opencode/haos-rootfs-direct/sys; do
  umount "$m" 2>/dev/null || true
done
' 2>/dev/null || true

echo "[1/9] Create $IMG_SIZE image from Raspbian boot layout"
cp -f "$BASE" "$OUT"
truncate -s "$IMG_SIZE" "$OUT"

echo "[2/9] Expand partition 2 to fill disk"
sudo parted -s "$OUT" resizepart 2 100% >/dev/null
LOOP=$(sudo losetup -fP --show "$OUT" 2>/dev/null)
sudo partprobe "$LOOP" 2>/dev/null || true
sudo e2fsck -fy "${LOOP}p2" >/dev/null 2>&1 || true
sudo resize2fs "${LOOP}p2" >/dev/null 2>&1

echo "[3/9] Format and mount"
sudo mkfs.ext4 -F -L HAROOT "${LOOP}p2" >/dev/null 2>&1
sudo mkdir -p /mnt/native-root /mnt/native-boot "$RASPSRC"
sudo mount -o rw "${LOOP}p2" /mnt/native-root
sudo mount -o rw "${LOOP}p1" /mnt/native-boot
RSRC_LOOP=$(sudo losetup -fP --show "$BASE" 2>/dev/null)
sudo mount -o ro "${RSRC_LOOP}p2" "$RASPSRC"

echo "[4/9] Copy native HA Core (Alpine armv6) root filesystem"
sudo cp -a "$HACORE"/. /mnt/native-root/

echo "[5/9] Copy kernel modules for Raspbian 6.1.21+ kernel"
sudo mkdir -p /mnt/native-root/lib/modules
sudo cp -a "$RASPSRC"/lib/modules/6.1.21+ /mnt/native-root/lib/modules/

# HA's bootstrap spawns a subprocess to find the user site dir; it needs /dev/null
sudo bash -c '
mkdir -p /mnt/native-root/dev/pts
for spec in "null c 1 3" "zero c 1 5" "random c 1 8" "urandom c 1 9" "tty c 5 0" "ptmx c 5 2"; do
  set -- $spec
  [ -e "/mnt/native-root/dev/$1" ] || mknod -m 666 "/mnt/native-root/dev/$1" "$2" "$3" "$4"
done
'

echo "[6/9] Bundle local-only SSH maintenance (dropbear, no cloud)"
sudo mkdir -p /mnt/native-root/opt/sshroot
sudo cp -a "$SSHROOT"/. /mnt/native-root/opt/sshroot/

# dropbear needs REAL character devices in its chroot. A plain cp can flatten
# them into regular files (urandom became a 32-byte file), and dropbear then
# refuses to start silently. Force real nodes here and again at boot.
sudo bash -c '
mkdir -p /mnt/native-root/opt/sshroot/dev/pts
rm -f /mnt/native-root/opt/sshroot/dev/urandom
for spec in "null c 1 3" "zero c 1 5" "random c 1 8" "urandom c 1 9" "tty c 5 0" "ptmx c 5 2"; do
  set -- $spec
  mknod -m 666 "/mnt/native-root/opt/sshroot/dev/$1" "$2" "$3" "$4"
done
'

# BusyBox in this rootfs has no modprobe applet, but the extracted one does.
# Copy it under that name so rc.local can load the USB Bluetooth driver.
sudo install -m 755 "$HACORE/bin/busybox" /mnt/native-root/sbin/modprobe

echo "[7/9] Seed local-only Home Assistant config"
sudo mkdir -p /mnt/native-root/config
# HACS 1.26.0, patched locally to work with GitHub's anonymous public API
# (no account/token needed). Config flow is skipped via YAML mode.
sudo mkdir -p /mnt/native-root/config/custom_components/hacs
sudo cp -a "$HACSBUNDLE"/. /mnt/native-root/config/custom_components/hacs/
# WoL helper used by the Samsung TV's HA "turn_on" action.
sudo install -m 755 "$WOLSCRIPT" /mnt/native-root/usr/local/bin/wol-tv55.sh
# Tustco Dashboard - our own local dashboard. Token is deliberately NOT baked
# in; run renew-dashboard-token.sh after flashing a fresh card.
sudo mkdir -p /mnt/native-root/config/tustco-dashboard
sudo cp -a "$DASHDIR"/. /mnt/native-root/config/tustco-dashboard/
# Keeps our dashboard pinned to the Lenovo Smart Display via Cast (no root).
sudo install -m 755 "$DIR/cast-pin.py" /mnt/native-root/usr/local/bin/cast-pin.py
# BEACON - our own TCF field interface (face/voice feedback), port 8125.
sudo mkdir -p /mnt/native-root/config/beacon
sudo cp -a "$DIR/../TustcoBeacon"/. /mnt/native-root/config/beacon/
# Tustco Circadian - offline adaptive lighting for our two RGBW bulbs.
# Includes the bundled eclipse calendar; no network at runtime.
sudo mkdir -p /mnt/native-root/config/tustco-circadian
sudo cp -a "$CIRCADIR"/. /mnt/native-root/config/tustco-circadian/
sudo rm -rf /mnt/native-root/config/tustco-circadian/__pycache__
# Tustco Presence - RF motion tripwire using the same bulbs. No reflash.
sudo mkdir -p /mnt/native-root/config/tustco-presence
sudo cp -a "$PRESENCEDIR"/. /mnt/native-root/config/tustco-presence/
sudo rm -rf /mnt/native-root/config/tustco-presence/__pycache__
sudo tee /mnt/native-root/config/configuration.yaml >/dev/null <<'YAML'
# LOCAL ONLY. No cloud, no analytics, no updater, no Google TTS.
homeassistant:
  name: Home
  latitude: 32.2226
  longitude: -110.9747

frontend:
http:
  server_host: 0.0.0.0
  server_port: 8123
api:
config:
onboarding:

# Bundled offline-safe integrations (default_config is NOT used: it pulls cloud).
recorder:
history:
logbook:
sun:
zone:
system_health:
map:
media_source:
usb:
ssdp:
zeroconf:

# UI helpers
input_boolean:
input_number:
input_select:
input_text:
input_datetime:
timer:
counter:

# Wake the curved Samsung from deep standby when HA turns it on.
shell_command:
  wake_tv_55: /usr/local/bin/wol-tv55.sh

# Samsung TV - persistent entry; HA retries even while the TV is off.
# The 32" set is controlled via its DLNA entity (its websocket needs a TV-side PIN).
samsungtv:
  - host: 192.168.1.152
    name: Samsung 6 Series (55)
    on_action:
      service: shell_command.wake_tv_55

# HACS in anonymous mode: no GitHub account or token required.
hacs:
  token: ""
  sidepanel_title: HACS
  sidepanel_icon: "hacs:hacs"

automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml
YAML
sudo sh -c 'for f in scripts scenes; do echo "[]" > /mnt/native-root/config/$f.yaml; done'
# HACS YAML-mode sensors only update on a repository event; refresh after boot.
sudo tee /mnt/native-root/config/automations.yaml >/dev/null <<'AUTO'
- alias: Refresh HACS sensor at startup
  trigger:
    - platform: homeassistant
      event: start
  action:
    - delay: "00:05:00"
    - service: homeassistant.update_entity
      target:
        entity_id: sensor.hacs
AUTO
# Seed the config entries HA already discovered overnight (both TVs, the
# Lenovo Cast display, and the Brother printer). Without this a fresh image
# would rediscover them but leave every flow waiting for a UI "Configure".
sudo mkdir -p /mnt/native-root/config/.storage
sudo cp "$CONFIGSEED" /mnt/native-root/config/.storage/core.config_entries
sudo tee /mnt/native-root/etc/hosts >/dev/null <<'HOSTS'
127.0.0.1 localhost homeassistant
::1 localhost ip6-localhost ip6-loopback
HOSTS
sudo tee /mnt/native-root/etc/hostname >/dev/null <<'HOSTNAME'
homeassistant
HOSTNAME

echo "[8/9] Configure native boot (busybox init, no OpenRC/s6/Docker)"
sudo tee /mnt/native-root/etc/inittab >/dev/null <<'INITTAB'
::sysinit:/bin/mount -t proc proc /proc
::sysinit:/bin/mount -t sysfs sysfs /sys
::sysinit:/bin/mkdir -p /dev/pts
::sysinit:/bin/mount -t devpts devpts /dev/pts
::sysinit:/sbin/mdev -s
::sysinit:/bin/hostname homeassistant
::sysinit:/bin/mkdir -p /config /run /var/log
::wait:/bin/sh /etc/rc.local
tty1::respawn:/bin/login -f root
::ctrlaltdel:/sbin/reboot
::shutdown:/bin/umount -a -r
INITTAB

sudo tee /mnt/native-root/etc/rc.local >/dev/null <<'RCLOCAL'
#!/bin/sh
# Local-only setup. No cloud, no DHCP dependency, no containers.
exec > /var/log/rc.local.log 2>&1
echo "=== native HA boot $(date -u) ==="

# Static network - never depends on a DHCP server
ip link set eth0 up
ip addr flush dev eth0
ip addr add 192.168.1.221/24 dev eth0
ip route add default via 192.168.1.1
# The stripped-down rootfs boots with no loopback address. Local services
# (HA API proxy, dashboard) cannot reach 127.0.0.1 without this.
ip link set lo up
ip addr add 127.0.0.1/8 dev lo
echo "nameserver 192.168.1.1" > /etc/resolv.conf
echo "network up:"
ip addr show eth0

# Pi 1 has no RTC - sync clock before HA starts
/usr/sbin/ntpd -n -q -p 192.168.1.1 -p pool.ntp.org

# Local maintenance SSH (dropbear in its own glibc root, LAN only)
mkdir -p /opt/sshroot/proc /opt/sshroot/sys /opt/sshroot/dev/pts
mount -t proc proc /opt/sshroot/proc 2>/dev/null
mount -t sysfs sysfs /opt/sshroot/sys 2>/dev/null
mount -t devpts devpts /opt/sshroot/dev/pts 2>/dev/null

# Rebuild the chroot's device nodes on every boot. A plain file copy can turn
# these character devices into regular files, and dropbear refuses to start.
for node in "null 1 3" "zero 1 5" "random 1 8" "urandom 1 9" "tty 5 0" "ptmx 5 2"; do
  set -- $node
  name=$1; major=$2; minor=$3
  if [ ! -c "/opt/sshroot/dev/$name" ]; then
    rm -f "/opt/sshroot/dev/$name"
    mknod "/opt/sshroot/dev/$name" c "$major" "$minor"
  fi
done
chmod 666 /opt/sshroot/dev/null /opt/sshroot/dev/zero /opt/sshroot/dev/random /opt/sshroot/dev/urandom /opt/sshroot/dev/tty /opt/sshroot/dev/ptmx
chroot /opt/sshroot /usr/sbin/dropbear -p 22
echo "dropbear exit=$?"

# Bluetooth: CSR USB dongle (0a12:0001) + BlueZ stack
/sbin/modprobe btusb
/usr/bin/dbus-daemon --system --fork
nohup /usr/lib/bluetooth/bluetoothd --experimental > /var/log/bluetoothd.log 2>&1 &
echo "bluetoothd pid $!"

# Start Home Assistant Core natively - no Docker, no wrapper
export PATH=/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin
echo "starting Home Assistant Core..."
nohup /usr/local/bin/hass --config /config --skip-pip > /var/log/home-assistant.log 2>&1 &
echo "hass pid $!"

# Tustco Dashboard - our own local dashboard on port 8124. No Docker, no cloud.
# It reads a long-lived HA token stored only on the Pi and never in the browser.
# setsid keeps it alive when a maintenance SSH session disconnects.
setsid /usr/local/bin/python3 /config/tustco-dashboard/server.py </dev/null >> /var/log/tustco-dashboard.log 2>&1 &
echo "dashboard started"

# Keep the Lenovo Smart Display showing our dashboard. Re-pins after reboots
# or if somebody casts something else to it. No root, no extra app.
setsid /usr/local/bin/python3 /usr/local/bin/cast-pin.py </dev/null >> /var/log/tustco-castpin.log 2>&1 &
echo "cast-pin started"

# BEACON - Tustco Cyber Force field interface. LAN only, no cloud.
setsid /usr/local/bin/python3 /config/beacon/beacon.py --port 8125 </dev/null >> /var/log/beacon.log 2>&1 &
echo "beacon started"

# Tustco Circadian - offline sun/moon/sky-event lighting rhythm. Wall switch
# stays authoritative for power; the daemon only sends Color and Dimmer.
setsid /usr/local/bin/python3 -u /config/tustco-circadian/circadian.py --daemon </dev/null >> /config/tustco-circadian/circadian.log 2>&1 &
echo "circadian started"

# Tustco Presence - coarse RF motion tripwire. Status page on port 8126.
mkdir -p /config/tustco-presence
setsid /usr/local/bin/python3 -u /config/tustco-presence/presence.py --daemon </dev/null >> /config/tustco-presence/presence.log 2>&1 &
echo "presence started"
RCLOCAL
sudo chmod 755 /mnt/native-root/etc/rc.local

sudo tee /mnt/native-boot/cmdline.txt >/dev/null <<'CMDLINE'
dwc_otg.lpm_enable=0 console=tty1 root=/dev/mmcblk0p2 rootfstype=ext4 rw rootwait fsck.repair=yes
CMDLINE

echo "[9/9] Verify and unmount"
sudo bash -c '
echo -n "hass: "; ls -l /mnt/native-root/usr/local/bin/hass | awk "{print \$5}"
echo -n "site-packages: "; du -sh /mnt/native-root/usr/local/lib/python3.9/site-packages | cut -f1
echo -n "modules: "; ls /mnt/native-root/lib/modules/ | tr "\n" " "; echo
echo -n "sshroot dropbear: "; ls -l /mnt/native-root/opt/sshroot/usr/sbin/dropbear | awk "{print \$5}"
echo -n "authorized_keys: "; stat -c "%s" /mnt/native-root/opt/sshroot/root/.ssh/authorized_keys
echo -n "modprobe: "; ls -l /mnt/native-root/sbin/modprobe | awk "{print \$5}"
echo -n "hacs files: "; find /mnt/native-root/config/custom_components/hacs -type f | wc -l
echo -n "config: "; stat -c "%s" /mnt/native-root/config/configuration.yaml
echo -n "circadian files: "; find /mnt/native-root/config/tustco-circadian -type f | wc -l
echo -n "presence files: "; find /mnt/native-root/config/tustco-presence -type f | wc -l
grep -E "ip addr add|dropbear|hass --config|circadian.py --daemon|presence.py --daemon" /mnt/native-root/etc/rc.local
'
sudo umount /mnt/native-boot
sudo umount /mnt/native-root
sudo umount "$RASPSRC"
sudo losetup -d "$RSRC_LOOP"
sudo losetup -d "$LOOP"
LOOP=""
RSRC_LOOP=""
sync

echo "DONE: $OUT"
ls -lh "$OUT"
