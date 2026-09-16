"""Speech-to-text via a managed whisper.cpp server subprocess (model loads once)."""

import asyncio
import io
import json
import logging

import aiohttp
import numpy as np
import soundfile as sf

from .. import config

log = logging.getLogger(__name__)

BUILD_DIRS = ["build-mac", "build-pi", "build"]


class WhisperSTT:
    def __init__(self, model: str = config.STT_MODEL, port: int = config.STT_PORT):
        self.model_path = config.WHISPER_DIR / "models" / f"ggml-{model}.bin"
        if not self.model_path.exists():
            raise FileNotFoundError(f"missing whisper model: {self.model_path}")
        self.binary = self._find_binary()
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.proc: asyncio.subprocess.Process | None = None
        self.session: aiohttp.ClientSession | None = None

    @staticmethod
    def _find_binary():
        for b in BUILD_DIRS:
            p = config.WHISPER_DIR / b / "bin" / "whisper-server"
            if p.exists():
                return p
        raise FileNotFoundError(
            "whisper-server not built — run: cmake --build sona_stt/whisper.cpp/build-mac "
            "--target whisper-server"
        )

    async def start(self):
        cmd = [
            str(self.binary),
            "-m",
            str(self.model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "-l",
            config.STT_LANGUAGE,
            "-nt",
            "-sns",
        ]
        self.proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        self.session = aiohttp.ClientSession()
        for _ in range(240):  # model load can take a few seconds (longer on the Pi)
            if self.proc.returncode is not None:
                raise RuntimeError("whisper-server exited during startup")
            try:
                async with self.session.get(self.url):
                    log.info("whisper-server ready (%s)", self.model_path.name)
                    return
            except aiohttp.ClientError:
                await asyncio.sleep(0.25)
        raise RuntimeError("whisper-server did not become ready")

    async def transcribe(self, pcm16: np.ndarray) -> str:
        buf = io.BytesIO()
        sf.write(buf, pcm16, config.SAMPLE_RATE, format="WAV", subtype="PCM_16")
        buf.seek(0)
        form = aiohttp.FormData()
        form.add_field("file", buf, filename="u.wav", content_type="audio/wav")
        form.add_field("temperature", "0.0")
        form.add_field("response_format", "json")
        async with self.session.post(f"{self.url}/inference", data=form) as resp:
            raw = await resp.text()
        try:
            text = json.loads(raw).get("text", "")
        except json.JSONDecodeError:
            text = raw
        return " ".join(text.split())

    async def stop(self):
        if self.session:
            await self.session.close()
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=3)
            except TimeoutError:
                self.proc.kill()
