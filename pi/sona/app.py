"""Sona orchestrator.

Examples:
  python -m sona.app                          # mic + mock DoA + mirror on :8765
  python -m sona.app --wav path/to/file.wav   # replay a wav instead of the mic
  python -m sona.app --doa sweep              # auto-rotating fake DoA
  python -m sona.app --doa xvf --g1           # ReSpeaker (USB firmware) DoA + real glasses
  python -m sona.app --doa serial             # fallback: ESP32 DoA over serial
  python -m sona.app --g1 --g1-bmp            # bitmap mode on the glasses
"""

import argparse
import asyncio
import logging
import time
import math
import numpy as np
import sounddevice as sd

from . import config
from .audio.capture import MicSource, WavSource
from .audio.vad import UtteranceSegmenter
from .display.g1 import G1
from .display.mirror import MirrorServer
from .display.renderer import Renderer
from .doa.mock import MockDoa
from .hub import Hub
from .state import SoundEvent, UiState
from .stt.sherpa_stream import SherpaStreamingSTT
from .summarize.llm import accept, refine
from .voice.speaker import OwnVoice

log = logging.getLogger("sona")

def utterance_dbfs(pcm: np.ndarray) -> float:
    """RMS loudness used ONLY to decide whether Whisper should run."""
    if pcm is None or len(pcm) == 0:
        return -120.0

    x = pcm.astype(np.float32)
    rms = float(np.sqrt(np.mean(x * x)))

    if rms < 1.0:
        return -120.0

    return 20.0 * math.log10(rms / 32768.0)

async def stt_worker(
    hub: Hub,
    state: UiState,
    stt: SherpaStreamingSTT,
    voice: OwnVoice,
):
    """
    Real-time streaming captions using Sherpa.

    Environmental sound detection is completely separate
    and remains untouched.
    """

    seg = UtteranceSegmenter()
    q = hub.subscribe("frames", maxsize=512)

    last_partial = ""
    utterance_started = False

    while True:
        frame = await q.get()

        was_active = seg.active

        utt = seg.push(frame)

        # ==========================================
        # SPEECH STARTED
        # ==========================================
        if seg.active and not was_active:

            stt.start_utterance()
            utterance_started = True
            last_partial = ""

            # Include the VAD preroll so we don't lose
            # the first word.
            initial_audio = seg.snapshot()

            if initial_audio is not None:
                text = stt.feed(initial_audio)

                level = utterance_dbfs(initial_audio)

                if (
                    level >= config.STT_MIN_DBFS
                    and text
                ):
                    hub.publish("partial", text)
                    last_partial = text

            continue

        # ==========================================
        # LIVE STREAMING
        # ==========================================
        if seg.active and utterance_started:

            text = stt.feed(frame)

            # Use the whole current utterance to estimate
            # whether the speaker is actually near.
            current = seg.snapshot()

            if current is None:
                continue

            level = utterance_dbfs(current)

            # Distant/background voice:
            # decode can continue internally but DO NOT
            # send captions to glasses.
            if level < config.STT_MIN_DBFS:
                if state.partial:
                    hub.publish("partial", "")
                continue

            if text and text != last_partial:

                hub.publish("partial", text)

                last_partial = text

            continue

        # ==========================================
        # UTTERANCE FINISHED
        # ==========================================
        if utt is not None and utterance_started:

            final_text = stt.finish()

            utterance_started = False

            hub.publish("partial", "")

            level = utterance_dbfs(utt)

            score = state.recent_speech()

            log.info(
                "STT candidate: level %.1f dBFS, speech %.2f",
                level,
                score if score is not None else -1,
            )

            # Near-voice filtering
            if level < config.STT_MIN_DBFS:
                log.info(
                    "STT ignored distant/quiet speech (%.1f dBFS)",
                    level,
                )
                continue

            # Existing YAMNet speech confidence gate
            if (
                score is not None
                and score < config.SPEECH_GATE_MIN
            ):
                log.info(
                    "STT ignored low speech confidence %.2f",
                    score,
                )
                continue

            if not final_text:
                continue

            t_end = time.time()
            t_start = (
                t_end
                - len(utt) / config.SAMPLE_RATE
            )

            angle = state.direction_between(
                t_start,
                t_end,
            )

            log.info(
                "heard LIVE (speech %.2f, %.1f dBFS, %s): %s",
                score if score is not None else -1,
                level,
                f"{angle:.0f}°"
                if angle is not None
                else "no bearing",
                final_text,
            )

            hub.publish(
                "transcript",
                {
                    "text": final_text,
                    "angle": angle,
                    "me": None,
                },
            )

async def state_worker(hub: Hub, state: UiState):
    caption_q = hub.subscribe("caption")
    transcript_q = hub.subscribe("transcript")
    cone_q = hub.subscribe("cone")
    names_q = hub.subscribe("name_set")
    partial_q = hub.subscribe("partial")
    speech_q = hub.subscribe("speech")
    sound_q = hub.subscribe("sound")
    name_q = hub.subscribe("name")
    doa_q = hub.subscribe("doa")
    mode_q = hub.subscribe("mode")

    async def captions():  # unconditional (mirror "simulate caption")
        while True:
            text = await caption_q.get()
            state.add_transcript(text, None, True)
            state.add_caption(text)

    async def transcripts():  # STT results: shown or hidden depending on mode + bearing
        while True:
            ev = await transcript_q.get()
            own = bool(ev.get("own"))
            allowed = state.caption_allowed(ev.get("angle")) and not own
            state.add_transcript(ev["text"], ev.get("angle"), allowed, me=ev.get("me"), own=own)
            if allowed:
                state.add_caption(ev["text"])
            elif not own:
                log.info("hidden in %s mode: %s", state.mode, ev["text"])

    async def cone():
        while True:
            state.cone_deg = float(await cone_q.get())
            state.dirty = True
            state.persist()
            log.info("focus cone -> %.0f°", state.cone_deg)

    async def name_settings():
        while True:
            raw = await names_q.get()
            state.names = [n.strip() for n in str(raw).split(",") if n.strip()]
            state.dirty = True
            state.persist()

    async def partials():
        while True:
            state.set_partial(await partial_q.get())

    async def speech():
        while True:
            state.note_speech(await speech_q.get())

    async def sounds():
        while True:
            ev = await sound_q.get()
            # bearing from readings NOT attributed to speech; keep the previous one if none
            angle = state.sound_direction()
            cur = state.active_sound()
            if angle is None and cur and cur.label == ev["label"]:
                angle = cur.angle
            state.set_sound(SoundEvent(label=ev["label"], score=ev.get("score", 0.0), angle=angle))

    async def names():
        while True:
            ev = await name_q.get()
            angle = ev["angle"] if ev.get("angle") is not None else state.speaker_direction()
            state.set_name(SoundEvent(label=ev["name"], kind="name", angle=angle))
            log.info(
                "NAME ALERT: %s at %s",
                ev["name"],
                f"{angle:.0f}°" if angle is not None else "unknown direction",
            )

    async def doa():
        while True:
            d = await doa_q.get()
            speech, moved = d.get("speech"), bool(d.get("moved"))
            state.record_doa(d.get("angle"), bool(d.get("active")), speech, moved)
            # a detected sound follows the bearing only while it moves WITHOUT speech —
            # with a talker present the chip's bearing points at the talker, not the siren
            if state.active_sound() and moved and not speech and d.get("angle") is not None:
                state.sound.angle = d["angle"]
            state.dirty = True

    async def mode():
        while True:
            m = await mode_q.get()
            if m not in config.MODES:
                continue
            state.mode = m
            state.dirty = True
            state.persist()
            log.info("mode -> %s", m)
            hub.publish("xvf_config", {"focus": m == "focus"})

    await asyncio.gather(
        captions(),
        transcripts(),
        cone(),
        name_settings(),
        partials(),
        speech(),
        sounds(),
        names(),
        doa(),
        mode(),
    )


async def g1_worker(state: UiState, g1: G1, renderer: Renderer, bmp_mode: bool):
    last_payload = None
    last_send = 0.0
    interval = config.G1_BMP_MIN_INTERVAL if bmp_mode else config.G1_TEXT_MIN_INTERVAL
    while True:
        await asyncio.sleep(0.05)
        if not g1.connected:
            continue
        now = time.time()
        if now - last_send < interval:
            continue
        payload = state.glass_text()
        if payload == last_payload:
            continue
        last_send, last_payload = now, payload
        try:
            if bmp_mode:
                await g1.send_bmp(renderer.to_bmp_bytes(renderer.render(state)))
            else:
                await g1.send_text(payload if payload else "--")
        except Exception as e:  # BLE hiccups must not kill the app
            log.warning("G1 send failed: %s", e)


async def housekeeping(state: UiState):
    """Time-based state changes that no event drives: clearing the page after silence."""
    while True:
        await asyncio.sleep(0.25)
        state.expire_idle()


def find_respeaker_mic() -> int | None:
    """Index of the reSpeaker XVF3800 input device, if plugged in."""
    for i, d in enumerate(sd.query_devices()):
        if "XVF3800" in d["name"] and d["max_input_channels"] > 0:
            return i
    return None


def respeaker_control_present() -> bool:
    try:
        import usb.core

        return usb.core.find(idVendor=0x2886, idProduct=0x001A) is not None
    except Exception:  # no libusb backend etc.
        return False


def build_parser():
    p = argparse.ArgumentParser(prog="sona", description="Sona glasses runtime")
    p.add_argument("--wav", help="replay a wav file instead of the microphone")
    p.add_argument("--loop-wav", action="store_true", help="loop the wav forever")
    p.add_argument("--mic-device", default=None, help="input device name/index")
    p.add_argument("--doa", default="mock", choices=["mock", "sweep", "serial", "gccphat", "xvf"])
    p.add_argument("--serial-port", default=None)
    p.add_argument("--g1", action="store_true", help="connect to real glasses over BLE")
    p.add_argument("--g1-bmp", action="store_true", help="bitmap mode instead of text mode")
    p.add_argument("--model", default=config.STT_MODEL, help="whisper model (base.en/small.en)")
    p.add_argument(
        "--name", default=None, help="wearer name(s) to alert on, comma-separated (default: config)"
    )
    p.add_argument("--no-stt", action="store_true")
    p.add_argument("--no-sounds", action="store_true")
    p.add_argument("--mirror-port", type=int, default=config.MIRROR_PORT)
    p.add_argument("-v", "--verbose", action="store_true")
    return p


async def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)-18s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    hub, state, renderer = Hub(), UiState(), Renderer()
    if state.restore():
        log.info(
            "restored settings: names=%s mode=%s cone=%.0f°",
            ", ".join(state.names),
            state.mode,
            state.cone_deg,
        )
    if args.name:
        state.names = [n.strip() for n in args.name.split(",") if n.strip()]
    own_voice = OwnVoice()
    state.voice = own_voice
    if own_voice.available:
        prof = (
            f"profile {own_voice.profile_seconds:.0f} s"
            if own_voice.profile is not None
            else "not enrolled"
        )
        log.info("own-voice recognition ready (%s; ignore=%s)", prof, state.ignore_own_voice)
    else:
        log.warning("own-voice recognition unavailable: %s", own_voice.reason)
    tasks: list = []

    # display
    mirror = MirrorServer(hub, state, renderer, port=args.mirror_port)
    await mirror.start()
    tasks.append(mirror.broadcast_loop())

    g1 = G1(dry_run=not args.g1)
    if args.g1:
        ok = await g1.connect()
        if not ok:
            log.error("continuing without glasses (mirror only)")
    tasks.append(g1_worker(state, g1, renderer, bmp_mode=args.g1_bmp))

    # audio in — prefer the reSpeaker array when it is plugged in
    mic = args.mic_device
    if mic is not None and mic.isdigit():
        mic = int(mic)
    if mic is None and not args.wav:
        mic = find_respeaker_mic()
        if mic is not None:
            log.info("reSpeaker XVF3800 detected — using it as the microphone")
    source = (
        WavSource(hub, args.wav, loop_file=args.loop_wav)
        if args.wav
        else MicSource(hub, device=mic)
    )
    tasks.append(source.run())

    # speech to text
    stt = None
    if not args.no_stt:
        stt = SherpaStreamingSTT()
        tasks.append(
            stt_worker(
                hub,
                state,
                stt,
                own_voice,
            )
        )

    # sound classification
    if not args.no_sounds:
        try:
            from .sounds.classifier import SoundClassifier

            tasks.append(SoundClassifier(hub, entries=state.sounds.entries()).run())
        except (ImportError, OSError, RuntimeError, ValueError) as e:
            log.error("sound classification disabled: %s", e)

    # name-call detection (needs the transcript, so only with STT on)
    if not args.no_stt:
        from .names.detector import NameDetector

        tasks.append(NameDetector(hub, state.names).run())

    # direction of arrival — default to the array's on-chip DoA when it is present
    if args.doa == "mock" and respeaker_control_present():
        args.doa = "xvf"
        log.info("reSpeaker XVF3800 control interface detected — using --doa xvf")
    if args.doa in ("mock", "sweep"):
        tasks.append(MockDoa(hub, sweep=args.doa == "sweep").run())
    elif args.doa == "serial":
        from .doa.xvf_serial import SerialDoa

        tasks.append(SerialDoa(hub, port=args.serial_port).run())
    elif args.doa == "gccphat":
        from .doa.gccphat import GccPhatDoa

        tasks.append(GccPhatDoa(hub).run())
    elif args.doa == "xvf":
        from .doa.xvf_usb import XvfUsbDoa

        tasks.append(XvfUsbDoa(hub).run())

    tasks.append(state_worker(hub, state))
    tasks.append(housekeeping(state))
    hub.publish("xvf_config", {"focus": state.mode == "focus"})

    log.info("sona is up — mirror: http://localhost:%d", args.mirror_port)
    try:
        await asyncio.gather(*tasks)
    finally:
        
        await g1.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbye")
