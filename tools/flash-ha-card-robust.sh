#!/usr/bin/env bash
# Robust flasher for the native no-Docker HA image onto the original Pi's card.
# Writes in 64 MiB chunks, retries a chunk up to 5 times if the USB card drops
# offline (the failure mode of the earlier plain dd), then verifies key files.
set -uo pipefail

IMG=/media/pdtust/AI/RaspberryPi/ha-native-pi1.img
CARD=/dev/sdd
LOG=/media/pdtust/AI/RaspberryPi/flash-progress.log
VERIFY=/tmp/opencode/ha-native-verify
CHUNK_MB=64
RETRIES=5

[ -f "$IMG" ] || { echo "MISSING IMAGE: $IMG" | tee -a "$LOG"; exit 1; }
sudo -v 2>/dev/null || true
mkdir -p "$(dirname "$LOG")" "$VERIFY"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }

total=$(stat -c '%s' "$IMG")
chunks=$(( (total + CHUNK_MB*1048576 - 1) / (CHUNK_MB*1048576) ))
log "START robust flash: $(basename "$IMG") ($total bytes) -> $CARD in $chunks x ${CHUNK_MB}MiB chunks"

# Make sure nothing is mounted on the card before writing.
sudo umount /media/devmon/bootfs /media/devmon/HAROOT 2>/dev/null || true
for p in "${CARD}"*; do
  mp=$(findmnt -no TARGET "$p" 2>/dev/null || true)
  [ -n "$mp" ] && sudo umount "$mp" && log "unmounted $p from $mp"
done

offset_mb=0
n=1
while [ $offset_mb -lt $(( total / 1048576 )) ]; do
  ok=0
  for attempt in $(seq 1 "$RETRIES"); do
    if timeout 300 sudo dd if="$IMG" of="$CARD" bs=1M \
        skip="$offset_mb" seek="$offset_mb" count="$CHUNK_MB" \
        conv=fsync status=none 2>>"$LOG"; then
      ok=1
      break
    fi
    log "chunk $n/$chunks at ${offset_mb}MiB FAILED (attempt $attempt/$RETRIES) - waiting for card"
    sleep 10
    # If the device vanished, wait for it to come back.
    for w in $(seq 1 30); do
      [ -b "$CARD" ] && break
      sleep 2
    done
  done
  if [ "$ok" -ne 1 ]; then
    log "ABORT: chunk $n at ${offset_mb}MiB unwritable after $RETRIES attempts"
    exit 1
  fi
  if [ $(( n % 8 )) -eq 0 ] || [ "$n" -eq "$chunks" ]; then
    log "progress: chunk $n/$chunks written ($(( offset_mb + CHUNK_MB ))MiB)"
  fi
  offset_mb=$(( offset_mb + CHUNK_MB ))
  n=$(( n + 1 ))
done

log "All $chunks chunks written. Re-reading partition table..."
sudo blockdev --rereadpt "$CARD" 2>/dev/null || true
sleep 3
sudo partprobe "$CARD" 2>/dev/null || true

# Verify the written image, not just the write calls.
rc=0
sudo mount "${CARD}1" "$VERIFY" 2>/dev/null || true
if grep -q 'root=/dev/mmcblk0p2' "$VERIFY/cmdline.txt" 2>/dev/null; then
  log "OK: native boot cmdline present"
else
  log "WARN: boot cmdline unexpected"; rc=1
fi
sudo umount "$VERIFY" 2>/dev/null || true

sudo mount "${CARD}2" "$VERIFY" 2>/dev/null || true
[ -x "$VERIFY/usr/local/bin/hass" ] && log "OK: hass binary present" || { log "WARN: hass missing"; rc=1; }
[ -s "$VERIFY/config/configuration.yaml" ] && log "OK: local-only config present" || { log "WARN: config missing"; rc=1; }
[ -s "$VERIFY/opt/sshroot/root/.ssh/authorized_keys" ] && log "OK: SSH key present" || { log "WARN: SSH key missing"; rc=1; }
sudo umount "$VERIFY" 2>/dev/null || true

if [ "$rc" -eq 0 ]; then
  log "FLASH COMPLETE AND VERIFIED. Move card to the Pi and power it on."
else
  log "FLASH WRITTEN BUT VERIFICATION FAILED - investigate before booting."
fi
exit "$rc"
