"""Minimal Even Realities G1 driver over BLE (bleak). Self-contained — no even_glasses
runtime dependency, so it runs lean on the Pi.

Protocol references:
 - official: https://github.com/even-realities/EvenDemoApp
 - community: https://github.com/emingenc/even_glasses ,
   https://github.com/AGiXT/mobile/blob/main/Even Realities G1 BLE Protocol.txt

Each arm (left/right) is its own BLE peripheral exposing a Nordic UART service.
Convention: send to LEFT first, then RIGHT. Both arms need a heartbeat or they drop.
IMPORTANT: the official Even app must be closed/disconnected while we drive them.
"""

import asyncio
import itertools
import json
import logging
import time
import zlib

from bleak import BleakClient, BleakScanner

from .. import config

log = logging.getLogger(__name__)

UART_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_WRITE = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_NOTIFY = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

BMP_CHUNK = 194
BMP_ADDRESS = bytes([0x00, 0x1C, 0x00, 0x00])
ADDR_CACHE = config.ROOT / "pi" / "g1_addresses.json"


class _Arm:
    def __init__(self, side: str, address: str, name: str):
        self.side = side
        self.address = address
        self.name = name
        self.client = BleakClient(address)
        self.lock = asyncio.Lock()

    async def connect(self):
        await self.client.connect()
        await self.client.start_notify(UART_NOTIFY, self._on_notify)
        log.info("connected %s arm: %s", self.side, self.name)

    def _on_notify(self, _sender, data: bytes):
        log.debug("G1 %s notify: %s", self.side, data.hex())

    async def write(self, data: bytes):
        async with self.lock:
            await self.client.write_gatt_char(UART_WRITE, data, response=True)


class G1:
    """dry_run=True logs every packet instead of touching BLE — used until glasses arrive."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.left: _Arm | None = None
        self.right: _Arm | None = None
        self._seq = itertools.cycle(range(256))
        self._hb_task: asyncio.Task | None = None
        self.connected = False

    # --- connection -------------------------------------------------------
    async def connect(self, scan_timeout: float = 12.0) -> bool:
        if self.dry_run:
            log.info("G1 dry-run mode: packets are logged, not sent")
            self.connected = True
            return True
        pair = self._load_cached() or await self._scan(scan_timeout)
        if not pair:
            log.error("no G1 glasses found (left+right). Is the Even app disconnected?")
            return False
        self.left, self.right = pair
        await asyncio.gather(self.left.connect(), self.right.connect())
        self._save_cache()
        # init/handshake byte from the official demo app flow; harmless if ignored
        await self._both(bytes([0x4D, 0xFB]))
        self._hb_task = asyncio.create_task(self._heartbeat())
        self.connected = True
        return True

    async def _scan(self, duration: float):
        log.info("scanning for G1 glasses (%.0f s)…", duration)
        devices = await BleakScanner.discover(timeout=duration)
        left = right = None
        for dev in devices:
            name = dev.name or ""
            if "_L_" in name:
                left = _Arm("left", dev.address, name)
            elif "_R_" in name:
                right = _Arm("right", dev.address, name)
        return (left, right) if left and right else None

    def _load_cached(self):
        try:
            data = json.loads(ADDR_CACHE.read_text())
            return (
                _Arm("left", data["left"], data.get("left_name", "G1 L")),
                _Arm("right", data["right"], data.get("right_name", "G1 R")),
            )
        except (OSError, KeyError, json.JSONDecodeError):
            return None

    def _save_cache(self):
        try:
            ADDR_CACHE.write_text(
                json.dumps(
                    {
                        "left": self.left.address,
                        "right": self.right.address,
                        "left_name": self.left.name,
                        "right_name": self.right.name,
                    }
                )
            )
        except OSError:
            pass

    async def _heartbeat(self):
        seq = 0
        while True:
            pkt = bytes([0x25, 0x06, 0x00, seq & 0xFF, 0x04, seq & 0xFF])
            await self._both(pkt)
            seq += 1
            await asyncio.sleep(5)

    # --- send helpers -----------------------------------------------------
    async def _both(self, data: bytes, gap: float = 0.05):
        if self.dry_run:
            log.debug("G1 dry-run send (%d bytes): %s…", len(data), data[:12].hex())
            return
        await self.left.write(data)
        await asyncio.sleep(gap)
        await self.right.write(data)

    # --- display API ------------------------------------------------------
    async def send_text(self, text: str):
        """Fast path: firmware renders the text (0x4E). ~40 chars x 5 lines per page."""
        lines = [line[: config.G1_TEXT_WIDTH] for line in text.split("\n")]
        lines = lines[: config.G1_TEXT_LINES]
        payload = "\n".join(lines).encode("utf-8")
        header = bytes(
            [
                0x4E,
                next(self._seq),
                1,
                0,
                config.G1_SCREEN_STATUS,
                0,
                0,
                1,
                1,
            ]
        )
        await self._both(header + payload)

    async def send_bmp(self, bmp: bytes):
        """Slow path: full-frame 1-bit 576x136 BMP (0x15 chunks + end + CRC)."""
        chunks = [bmp[i : i + BMP_CHUNK] for i in range(0, len(bmp), BMP_CHUNK)]
        crc = zlib.crc32(BMP_ADDRESS + bmp) & 0xFFFFFFFF
        crc_pkt = bytes([0x16]) + crc.to_bytes(4, "big")
        t0 = time.time()
        for arm in (self.left, self.right) if not self.dry_run else (None,):
            for seq, chunk in enumerate(chunks):
                head = bytes([0x15, seq & 0xFF]) + (BMP_ADDRESS if seq == 0 else b"")
                if self.dry_run:
                    continue
                await arm.write(head + chunk)
            if not self.dry_run:
                await arm.write(bytes([0x20, 0x0D, 0x0E]))
                await arm.write(crc_pkt)
        log.info("bmp frame sent (%d chunks/arm, %.2f s)", len(chunks), time.time() - t0)

    async def clear(self):
        await self._both(bytes([0xF5, 0x18, 0x00, 0x00, 0x00]))

    async def disconnect(self):
        if self._hb_task:
            self._hb_task.cancel()
        for arm in (self.left, self.right):
            if arm and arm.client.is_connected:
                await arm.client.disconnect()
        self.connected = False
