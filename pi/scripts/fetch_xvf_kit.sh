#!/usr/bin/env bash
# Fetch Seeed's ReSpeaker XVF3800 kit — firmware images, DFU guide, DoA diagram and the xvf_host
# control tools — from their public GitHub repo. Not committed here: that repo carries no license,
# so we don't redistribute; the setup scripts call this instead. Re-runnable, skips present files.
set -euo pipefail
ROOT="${SONA_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
REPO="respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY"
RAW="https://raw.githubusercontent.com/$REPO/master"
API="https://api.github.com/repos/$REPO/contents"

get() {  # url dst
  [ -s "$2" ] && return 0
  mkdir -p "$(dirname "$2")"
  curl -fsSL -o "$2" "$1" && echo "  fetched $(basename "$2")"
}

echo "==> firmware images + docs -> firmware/xvf3800/"
for f in respeaker_xvf3800_usb_dfu_firmware_v2.1.0_16k6ch.bin respeaker_xvf3800_usb_dfu_firmware_v2.1.0.bin; do
  get "$RAW/xmos_firmwares/usb/$f" "$ROOT/firmware/xvf3800/$f"
done
get "$RAW/xmos_firmwares/i2s/respeaker_xvf3800_i2s_dfu_firmware_v1.0.7.bin" \
    "$ROOT/firmware/xvf3800/respeaker_xvf3800_i2s_dfu_firmware_v1.0.7.bin"
get "$RAW/xmos_firmwares/dfu_guide.md" "$ROOT/firmware/xvf3800/dfu_guide.md"
get "$RAW/doc/doa.jpg" "$ROOT/firmware/xvf3800/doa_convention.jpg"

echo "==> host-control tools -> tools/xvf_host/"
fetch_dir() {  # <repo path> <local dir>
  curl -fsSL "$API/$1" \
    | python3 -c 'import sys, json; [print(e["name"], e["download_url"]) for e in json.load(sys.stdin) if e["type"] == "file"]' \
    | while read -r name url; do get "$url" "$2/$name"; done
  chmod +x "$2"/xvf_host "$2"/xvf_i2c_dfu 2>/dev/null || true
}
fetch_dir host_control/mac_arm64 "$ROOT/tools/xvf_host/mac_arm64"
fetch_dir host_control/rpi_64bit "$ROOT/tools/xvf_host/rpi_64bit"
fetch_dir python_control        "$ROOT/tools/xvf_host/python"
echo "done — $(du -sh "$ROOT/tools/xvf_host" | cut -f1) of tools, $(du -sh "$ROOT/firmware/xvf3800" | cut -f1) of firmware"
