"""DoA from the XIAO ESP32S3 on the ReSpeaker XVF3800 over USB serial.

Expects lines like 'DOA:123,VAD:1' from firmware/esp32_doa/esp32_doa.ino.
Reconnects forever, so the app survives unplugging the hat.
"""

import asyncio
import glob
import logging

import serial

from .. import config

log = logging.getLogger(__name__)

PORT_PATTERNS = [
    "/dev/cu.usbmodem*",  # macOS
    "/dev/ttyACM*",  # Raspberry Pi
    "/dev/ttyUSB*",
]


def find_port() -> str | None:
    for pat in PORT_PATTERNS:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


class SerialDoa:
    def __init__(self, hub, port: str | None = None, baud: int = config.SERIAL_BAUD):
        self.hub = hub
        self.port = port
        self.baud = baud

    def _read_lines(self, ser):
        return ser.readline().decode("ascii", errors="ignore").strip()

    async def run(self):
        while True:
            port = self.port or find_port()
            if not port:
                log.warning("no serial port found for the mic array, retrying…")
                await asyncio.sleep(2)
                continue
            try:
                ser = serial.Serial(port, self.baud, timeout=1)
                log.info("DoA serial connected: %s", port)
                while True:
                    line = await asyncio.to_thread(self._read_lines, ser)
                    if not line.startswith("DOA:"):
                        continue
                    try:
                        parts = dict(p.split(":") for p in line.split(","))
                        angle = (float(parts["DOA"]) + config.AZIMUTH_OFFSET_DEG) % 360
                        active = parts.get("VAD", "0").strip() == "1"
                    except (ValueError, KeyError):
                        continue
                    self.hub.publish(
                        "doa", {"angle": angle, "active": active, "speech": active, "moved": True}
                    )
            except (serial.SerialException, OSError) as e:
                log.warning("DoA serial lost (%s), reconnecting…", e)
                await asyncio.sleep(2)
