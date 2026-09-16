"""Groups 30 ms frames into utterances. WebRTC VAD with an adaptive-energy fallback."""

import logging
from collections import deque

import numpy as np

from .. import config

log = logging.getLogger(__name__)

try:
    import webrtcvad

    _HAVE_WEBRTC = True
except ImportError:  # pragma: no cover
    _HAVE_WEBRTC = False
    log.warning("webrtcvad not available, using energy VAD fallback")


class UtteranceSegmenter:
    def __init__(self):
        self.vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS) if _HAVE_WEBRTC else None
        n_window = config.VAD_TRIGGER_WINDOW_MS // config.FRAME_MS
        self.window: deque[bool] = deque(maxlen=n_window)
        self.preroll: deque[np.ndarray] = deque(maxlen=n_window + 3)
        self.buf: list[np.ndarray] = []
        self.active = False
        self.silence_ms = 0
        self._floor = 200.0  # adaptive noise floor for the fallback VAD

    @property
    def duration_s(self) -> float:
        return len(self.buf) * config.FRAME_MS / 1000

    def snapshot(self) -> np.ndarray | None:
        """Copy of the in-progress utterance, for partial transcription."""
        if not self.active or not self.buf:
            return None
        return np.concatenate(self.buf)

    def _is_speech(self, frame: np.ndarray) -> bool:
        if self.vad is not None:
            return self.vad.is_speech(frame.tobytes(), config.SAMPLE_RATE)
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)) + 1e-6)
        self._floor = 0.995 * self._floor + 0.005 * rms
        return rms > max(3.0 * self._floor, 300.0)

    def push(self, frame: np.ndarray) -> np.ndarray | None:
        """Feed one frame; returns a finished utterance (int16 pcm) or None."""
        voiced = self._is_speech(frame)

        if not self.active:
            self.preroll.append(frame)
            self.window.append(voiced)
            if (
                len(self.window) == self.window.maxlen
                and sum(self.window) / len(self.window) >= config.VAD_TRIGGER_RATIO
            ):
                self.active = True
                self.silence_ms = 0
                self.buf = list(self.preroll)
                self.window.clear()
            return None

        self.buf.append(frame)
        self.silence_ms = 0 if voiced else self.silence_ms + config.FRAME_MS
        dur_s = len(self.buf) * config.FRAME_MS / 1000

        if self.silence_ms >= config.VAD_END_SILENCE_MS or dur_s >= config.UTTERANCE_MAX_S:
            self.active = False
            self.preroll.clear()
            utterance = np.concatenate(self.buf)
            self.buf = []
            if dur_s - self.silence_ms / 1000 >= config.UTTERANCE_MIN_S:
                return utterance
        return None
