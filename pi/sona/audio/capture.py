"""Audio sources. Both publish np.int16 mono 30 ms frames @16 kHz to hub topic 'frames'."""

import asyncio
import logging

import numpy as np
import sounddevice as sd
import soundfile as sf

from .. import config

log = logging.getLogger(__name__)


def _resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return x
    n_out = round(len(x) * sr_to / sr_from)
    xp = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    xq = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(xq, xp, x.astype(np.float32)).astype(np.int16)


class MicSource:
    """Input device -> frames. Multi-channel devices (the reSpeaker) contribute one channel
    (config.MIC_CHANNEL); falls back to the device's native rate + resampling if needed."""

    def __init__(self, hub, device: int | str | None = None, channel: int | None = None):
        self.hub = hub
        self.device = device
        self.channel = channel

    async def run(self):
        loop = asyncio.get_running_loop()
        try:
            info = sd.query_devices(self.device, "input")
        except (sd.PortAudioError, ValueError, OSError) as e:
            # a Pi with only the glasses attached has no mic: keep mirror + glasses running
            log.error(
                "no microphone available (%s) — captions and sound detection are OFF. "
                "Plug in the reSpeaker or a USB mic, or run with --wav <file>.",
                e,
            )
            await asyncio.Event().wait()
        n_ch = 2 if int(info["max_input_channels"]) >= 2 else 1
        ch = min(self.channel if self.channel is not None else config.MIC_CHANNEL, n_ch - 1)

        def make_cb(native_rate: int):
            residual = np.zeros(0, dtype=np.int16)

            def cb(indata, frames, t, status):
                nonlocal residual
                if status:
                    log.debug("mic status: %s", status)
                data = np.frombuffer(bytes(indata), dtype=np.int16)
                if n_ch > 1:
                    data = np.ascontiguousarray(data.reshape(-1, n_ch)[:, ch])
                data = _resample(data, native_rate, config.SAMPLE_RATE)
                residual = np.concatenate([residual, data])
                while len(residual) >= config.FRAME_SAMPLES:
                    frame = residual[: config.FRAME_SAMPLES].copy()
                    residual = residual[config.FRAME_SAMPLES :]
                    loop.call_soon_threadsafe(self.hub.publish, "frames", frame)

            return cb

        def open_stream(rate: int):
            stream = sd.RawInputStream(
                samplerate=rate,
                channels=n_ch,
                dtype="int16",
                blocksize=int(rate * config.FRAME_MS / 1000),
                device=self.device,
                callback=make_cb(rate),
            )
            stream.start()
            return stream

        rate = config.SAMPLE_RATE
        try:
            stream = open_stream(rate)
        except sd.PortAudioError:
            rate = int(info["default_samplerate"])
            log.warning("16 kHz capture unsupported, using native %d Hz + resample", rate)
            try:
                stream = open_stream(rate)
            except sd.PortAudioError as e:
                log.error("could not open the microphone (%s) — captions are OFF", e)
                await asyncio.Event().wait()

        log.info("microphone: %s — channel %d of %d @ %d Hz", info["name"], ch + 1, n_ch, rate)
        try:
            await asyncio.Event().wait()  # run until cancelled
        finally:
            stream.stop()
            stream.close()


class WavSource:
    """Replay a wav file as if it were live mic input (tests / demos without a mic)."""

    def __init__(self, hub, path: str, realtime: bool = True, loop_file: bool = False):
        self.hub = hub
        self.path = path
        self.realtime = realtime
        self.loop_file = loop_file

    async def run(self):
        wav, sr = sf.read(self.path, dtype="int16")
        if wav.ndim > 1:
            wav = wav[:, 0]
        wav = _resample(wav, sr, config.SAMPLE_RATE)
        # trailing silence so the VAD closes the final utterance
        wav = np.concatenate([wav, np.zeros(config.SAMPLE_RATE, dtype=np.int16)])
        log.info("replaying %s (%.1f s)", self.path, len(wav) / config.SAMPLE_RATE)
        while True:
            for start in range(0, len(wav) - config.FRAME_SAMPLES, config.FRAME_SAMPLES):
                self.hub.publish("frames", wav[start : start + config.FRAME_SAMPLES])
                if self.realtime:
                    await asyncio.sleep(config.FRAME_MS / 1000)
            if not self.loop_file:
                log.info("wav replay finished")
                return
