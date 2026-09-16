"""DoA + speech flag straight from the XVF3800 over USB — no ESP32 in the loop — plus
mode-dependent configuration of the array (focus mode fixes a beam to the front).

Requires the USB firmware (see firmware/xvf3800/README.md) and pyusb/libusb. The control
interface is plain USB vendor requests, mirroring Seeed's python_control/xvf_host.py:
  read : ctrl_transfer(IN  | VENDOR | DEVICE, bRequest=0, wValue=cmd | 0x80, wIndex=resid, n+1)
  write: ctrl_transfer(OUT | VENDOR | DEVICE, bRequest=0, wValue=cmd,        wIndex=resid, payload)
The first response byte is a status: 0 = ok, 64 = busy/retry.

Angle convention: the XVF3800 reports 0..359 with 0 at the connector (cable) edge
(firmware/xvf3800/doa_convention.jpg). Worn with the cable at the back of the head, that edge
is 180° in Sona's frame (0 = wearer's front, clockwise), hence AZIMUTH_OFFSET_DEG = 180 and
XVF_DOA_SIGN = +1; flip the sign if the board is mounted component-side down.

Focus mode: the chip's focused beam 1 is fixed at the wearer's front and its ASR output is
routed to USB channel 2 (the channel STT listens to), so speech from the sides/back is
attenuated before Whisper ever hears it. Channel 1 keeps the 360° auto-select beam.

Bench test:   .venv/bin/python -m sona.doa.xvf_usb [seconds]
"""

import asyncio
import logging
import math
import struct
import sys
import time

import usb.core
import usb.util

from .. import config

log = logging.getLogger(__name__)

VID, PID = 0x2886, 0x001A

# name -> (resid, cmdid, count, type) — subset of Seeed's command map (tools/xvf_host/python)
PARAMS = {
    "VERSION": (48, 0, 3, "u8"),
    "BLD_MSG": (48, 1, 50, "char"),
    "SAVE_CONFIGURATION": (48, 9, 1, "u8"),
    "AEC_MIC_ARRAY_GEO": (33, 74, 12, "f32"),  # 4 mics x (x, y, z) metres
    "AEC_AZIMUTH_VALUES": (33, 75, 4, "f32"),  # radians: beam1, beam2, free-running, auto
    "AEC_SPENERGY_VALUES": (33, 80, 4, "f32"),  # speech energy per beam, >0 = speech
    "AEC_FIXEDBEAMSAZIMUTH_VALUES": (33, 81, 2, "f32"),  # radians for fixed beams 1, 2
    "AEC_FIXEDBEAMSGATING": (33, 83, 1, "u8"),  # 1: silence the fixed beam without speech
    "AEC_FIXEDBEAMSONOFF": (33, 37, 1, "i32"),  # 1: focused beams stay where we put them
    "AUDIO_MGR_OP_L": (35, 15, 2, "u8"),  # (category, source) for USB channel 1
    "AUDIO_MGR_OP_R": (35, 19, 2, "u8"),  # (category, source) for USB channel 2
    "LED_EFFECT": (20, 12, 1, "u8"),  # 0 off, 1 breath, 2 rainbow, 3 colour, 4 doa, 5 ring
    "DOA_VALUE": (20, 18, 2, "u16"),  # [angle 0..359, speech 0/1]
}
_SIZE = {"u8": 1, "char": 1, "u16": 2, "i32": 4, "f32": 4}
_FMT = {"u8": "B", "char": "c", "u16": "H", "i32": "i", "f32": "f"}
_IN = usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE
_OUT = usb.util.CTRL_OUT | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE

# output router (category, source): 7 = ASR outputs, source = beam index
ROUTE_ASR_FIXED_BEAM_1 = (7, 0)
ROUTE_ASR_AUTO_SELECT = (7, 3)  # firmware default for channel 2


def to_sona_angle(raw_deg: float) -> float:
    return (config.XVF_DOA_SIGN * raw_deg + config.AZIMUTH_OFFSET_DEG) % 360


def to_xvf_angle(sona_deg: float) -> float:
    return (config.XVF_DOA_SIGN * (sona_deg - config.AZIMUTH_OFFSET_DEG)) % 360


class XvfDevice:
    TIMEOUT_MS = 2000

    def __init__(self):
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise RuntimeError(
                "XVF3800 not found on USB — USB firmware flashed? cable in the XMOS port "
                "(beside the 3.5 mm jack)?"
            )

    def read(self, name: str):
        resid, cmd, count, typ = PARAMS[name]
        n = count * _SIZE[typ]
        for _attempt in range(8):  # status 64 = device busy; the reference tool retries too
            raw = bytes(self.dev.ctrl_transfer(_IN, 0, cmd | 0x80, resid, n + 1, self.TIMEOUT_MS))
            if raw and raw[0] == 0:
                break
            time.sleep(0.02)
        else:
            raise RuntimeError(f"{name}: device status {raw[0] if raw else 'empty'}")
        vals = struct.unpack("<" + _FMT[typ] * count, raw[1 : 1 + n])
        if typ == "char":
            return b"".join(vals).split(b"\0")[0].decode(errors="ignore")
        return list(vals)

    def write(self, name: str, values) -> None:
        resid, cmd, count, typ = PARAMS[name]
        payload = struct.pack("<" + _FMT[typ] * count, *values)
        self.dev.ctrl_transfer(_OUT, 0, cmd, resid, payload, self.TIMEOUT_MS)

    def doa(self) -> tuple[int, bool]:
        angle, speech = self.read("DOA_VALUE")
        return int(angle), bool(speech)

    def set_focus(self, on: bool, front_sona_deg: float = 0.0) -> None:
        """Focus on: fix beam 1 at the wearer's front and feed its ASR output to channel 2.
        Focus off: back to the firmware default (auto-select beam on channel 2)."""
        if on:
            a = math.radians(to_xvf_angle(front_sona_deg))
            self.write("AEC_FIXEDBEAMSAZIMUTH_VALUES", [a, a])
            self.write("AEC_FIXEDBEAMSGATING", [0])  # never silence the front beam
            self.write("AEC_FIXEDBEAMSONOFF", [1])
            self.write("AUDIO_MGR_OP_R", list(ROUTE_ASR_FIXED_BEAM_1))
        else:
            self.write("AEC_FIXEDBEAMSONOFF", [0])
            self.write("AUDIO_MGR_OP_R", list(ROUTE_ASR_AUTO_SELECT))

    def describe_focus(self) -> str:
        on = self.read("AEC_FIXEDBEAMSONOFF")[0]
        az = [round(math.degrees(v)) for v in self.read("AEC_FIXEDBEAMSAZIMUTH_VALUES")]
        route = tuple(self.read("AUDIO_MGR_OP_R"))
        return f"fixed_beams={'on' if on else 'off'} azimuths={az} ch2_route={route}"

    def close(self) -> None:
        usb.util.dispose_resources(self.dev)


class XvfUsbDoa:
    """Polls DOA_VALUE and publishes hub 'doa'; applies focus/surround configuration to the
    array when the app publishes 'xvf_config' {"focus": bool}."""

    def __init__(self, hub, hz: float = 10.0):
        self.hub = hub
        self.hz = hz
        self.cfg_q = hub.subscribe("xvf_config")
        self.focus = config.DEFAULT_MODE == "focus"

    def _drain_config(self) -> bool:
        changed = False
        while not self.cfg_q.empty():
            msg = self.cfg_q.get_nowait()
            want = bool(msg.get("focus"))
            changed |= want != self.focus
            self.focus = want
        return changed

    def _apply(self, dev: XvfDevice) -> None:
        if not config.XVF_FIXED_BEAM:
            return
        try:
            dev.set_focus(self.focus)
            log.info(
                "array configured for %s: %s",
                "focus" if self.focus else "surround",
                dev.describe_focus(),
            )
        except (RuntimeError, usb.core.USBError) as e:
            log.warning("could not configure the array: %s", e)

    async def run(self):
        while True:
            try:
                dev = await asyncio.to_thread(XvfDevice)
                ver = ".".join(map(str, dev.read("VERSION")))
                log.info("XVF3800 connected: firmware %s (%s)", ver, dev.read("BLD_MSG"))
                self._drain_config()
                await asyncio.to_thread(self._apply, dev)
                last_angle, last_change = None, 0.0
                while True:
                    if self._drain_config():
                        await asyncio.to_thread(self._apply, dev)
                    angle, speech = await asyncio.to_thread(dev.doa)
                    now = time.time()
                    moved = angle != last_angle
                    if moved:
                        last_angle, last_change = angle, now
                    # DOA_VALUE holds its last estimate forever; treat it as live while speech
                    # is flagged or the estimate moved recently (non-speech sounds move it too)
                    active = speech or (now - last_change) < config.XVF_DOA_HOLD_S
                    self.hub.publish(
                        "doa",
                        {
                            "angle": to_sona_angle(angle),
                            "active": active,
                            "speech": speech,  # the chip's own flag: is this bearing a talker?
                            "moved": moved,
                        },
                    )
                    await asyncio.sleep(1 / self.hz)
            except (RuntimeError, usb.core.USBError) as e:
                log.warning("XVF3800 DoA unavailable (%s); retrying in 2 s", e)
                await asyncio.sleep(2)


def _bench(seconds: float = 15.0) -> int:
    try:
        dev = XvfDevice()
    except RuntimeError as e:
        print(e)
        return 1
    print("VERSION      :", ".".join(map(str, dev.read("VERSION"))))
    print("BLD_MSG      :", dev.read("BLD_MSG"))
    try:
        geo = dev.read("AEC_MIC_ARRAY_GEO")
        print(
            "MIC GEOMETRY :", [tuple(round(v, 3) for v in geo[i : i + 3]) for i in range(0, 12, 3)]
        )
    except RuntimeError as e:
        print("MIC GEOMETRY : (unavailable:", e, ")")
    print("BEAM CONFIG  :", dev.describe_focus())
    print(f"\nstreaming DOA for {seconds:.0f} s — talk / clap from different sides:")
    t_end = time.time() + seconds
    while time.time() < t_end:
        angle, speech = dev.doa()
        az = dev.read("AEC_AZIMUTH_VALUES")
        sp = dev.read("AEC_SPENERGY_VALUES")
        bar = "#" * min(40, int(sp[3] / 200000))
        print(
            f"  DOA {angle:3d}°  speech={int(speech)}  sona={to_sona_angle(angle):5.1f}°  "
            f"auto-beam={az[3] * 57.2958:6.1f}°  spenergy {bar}",
            flush=True,
        )
        time.sleep(0.2)
    dev.close()
    return 0


if __name__ == "__main__":
    sys.exit(_bench(float(sys.argv[1]) if len(sys.argv) > 1 else 15.0))
