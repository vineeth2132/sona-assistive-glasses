#!/usr/bin/env bash
# Sona — what is plugged in right now? Run after connecting the ReSpeaker / XIAO / G1.
# Works on macOS and Raspberry Pi OS.
cd "$(dirname "$0")/.."
echo "=== USB devices (XMOS / ReSpeaker / Seeed / Espressif) ==="
if [[ "$(uname)" == "Darwin" ]]; then
  system_profiler SPUSBDataType 2>/dev/null \
    | grep -i -B1 -A8 "xmos\|respeaker\|seeed\|espressif\|xiao\|dfu" \
    | grep -i "product id\|vendor id\|serial number\|manufacturer\|^ *[A-Za-z].*:$" || echo "(none)"
else
  lsusb | grep -i "xmos\|respeaker\|seeed\|espressif\|20b1\|2886\|303a" || echo "(none)"
fi
echo
echo "=== DFU-capable devices (dfu-util -l) ==="
command -v dfu-util >/dev/null && dfu-util -l 2>/dev/null | grep -i "found\|dfu" || echo "(dfu-util not installed or none)"
echo
echo "=== Audio devices (sounddevice) ==="
.venv/bin/python -m sounddevice 2>&1 || echo "(venv missing?)"
echo
echo "=== Serial ports ==="
ls /dev/cu.usbmodem* /dev/cu.usbserial* /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || echo "(none)"
