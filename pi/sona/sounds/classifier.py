"""Environmental sound classification with YAMNet (521 AudioSet classes, tflite).

Publishes hub topic 'sound' with the highest-priority target class above threshold.
"""

import asyncio
import logging
import time

import numpy as np

from .. import config
from .watchlist import SoundWatchlist, load_class_names

log = logging.getLogger(__name__)


def _load_interpreter(path: str):
    try:
        from ai_edge_litert.interpreter import Interpreter  # Mac + modern Pi wheels
    except ImportError:
        try:
            from tflite_runtime.interpreter import Interpreter  # classic Pi wheel
        except ImportError:
            import tensorflow as tf  # last resort

            Interpreter = tf.lite.Interpreter
    return Interpreter(model_path=path)


class SoundClassifier:
    WINDOW = 15600  # fixed model input: 0.975 s @ 16 kHz

    def __init__(self, hub, entries: list[dict] | None = None):
        self.hub = hub
        self.targets_q = hub.subscribe("sound_targets")  # live edits from the mirror
        self.interp = _load_interpreter(str(config.YAMNET_MODEL))
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.out = self.interp.get_output_details()[0]
        self.names = load_class_names()
        self.targets: dict[int, tuple[str, int, float]] = {}
        self.set_watchlist(entries if entries is not None else SoundWatchlist(self.names).entries())

        self.smoothed = np.zeros(len(self.names), dtype=np.float32)
        self.speech_score = 0.0
        self._last_log: dict[str, float] = {}

    def set_watchlist(self, entries: list[dict]) -> None:
        """class index -> (label, priority, threshold) for the enabled entries."""
        targets: dict[int, tuple[str, int, float]] = {}
        for e in entries:
            if not e.get("enabled", True):
                continue
            for name in e["classes"]:
                if name in self.names:
                    targets[self.names.index(name)] = (e["label"], e["priority"], e["threshold"])
        self.targets = targets
        log.info(
            "YAMNet watching %d classes for: %s",
            len(targets),
            ", ".join(sorted({t[0] for t in targets.values()})) or "(nothing)",
        )

    def _infer(self, wav: np.ndarray) -> np.ndarray:
        self.interp.set_tensor(self.inp["index"], wav.astype(np.float32))
        self.interp.invoke()
        return self.interp.get_tensor(self.out["index"]).reshape(-1)

    async def run(self):
        q = self.hub.subscribe("frames", maxsize=256)
        targets_q = self.targets_q
        buf = np.zeros(0, dtype=np.float32)
        hop = int(config.SOUND_HOP_S * config.SAMPLE_RATE)
        since_infer = 0
        while True:
            frame = await q.get()
            while not targets_q.empty():
                self.set_watchlist(targets_q.get_nowait())
            f32 = frame.astype(np.float32) / 32768.0
            buf = np.concatenate([buf, f32])[-self.WINDOW :]
            since_infer += len(f32)
            if len(buf) < self.WINDOW or since_infer < hop:
                continue
            since_infer = 0
            scores = await asyncio.to_thread(self._infer, buf.copy())
            a = config.SOUND_EMA_ALPHA
            self.smoothed = a * scores + (1 - a) * self.smoothed
            self.speech_score = float(self.smoothed[0])  # AudioSet class 0 = Speech
            self.hub.publish("speech", self.speech_score)
            self._emit()

    def _emit(self):
        best: tuple[int, float, str] | None = None  # (priority, score, label)
        for idx, (label, prio, thr) in self.targets.items():
            s = float(self.smoothed[idx])
            if s >= thr and (best is None or (prio, s) > (best[0], best[1])):
                best = (prio, s, label)
        if best is None:
            return
        prio, score, label = best
        now = time.time()
        if now - self._last_log.get(label, 0) > config.SOUND_LOG_COOLDOWN_S:
            log.info("sound detected: %s (%.2f)", label, score)
            self._last_log[label] = now
        self.hub.publish("sound", {"label": label, "score": score})
