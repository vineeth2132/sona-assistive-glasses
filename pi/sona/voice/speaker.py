"""Own-voice recognition (speaker verification).

The wearer enrols once (~20 s of natural speech); every finished utterance is then embedded
with a speaker model and compared to that profile by cosine similarity. Matching utterances
can be hidden — the wearer doesn't want their own words on the display.

Model: WeSpeaker CAM++ (VoxCeleb) via sherpa-onnx — ~30 MB, tens of ms per utterance on the
Mac, well under a second on the Pi. Profile is stored in out/voice_profile.json.
"""

import json
import logging

import numpy as np

from .. import config

log = logging.getLogger(__name__)
PROFILE_PATH = config.ROOT / "out" / "voice_profile.json"


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


class OwnVoice:
    def __init__(self):
        self.available = False
        self.reason = ""
        self._extractor = None
        self.profile: np.ndarray | None = None
        self.profile_seconds = 0.0
        self.enrolling = False
        self._acc: np.ndarray | None = None
        self._acc_seconds = 0.0
        self._load_model()
        self._load_profile()

    # --- model ---
    def _load_model(self) -> None:
        if not config.OWN_VOICE_MODEL.exists():
            self.reason = f"model missing: {config.OWN_VOICE_MODEL.name} (see pi/setup.sh)"
            return
        try:
            import sherpa_onnx
        except ImportError:
            self.reason = "sherpa-onnx not installed"
            return
        try:
            cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(config.OWN_VOICE_MODEL), num_threads=1, debug=False, provider="cpu"
            )
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
            self.available = True
        except Exception as e:  # any load failure just disables the feature
            self.reason = f"model failed to load: {e}"

    def embed(self, pcm16: np.ndarray) -> np.ndarray | None:
        if not self.available:
            return None
        stream = self._extractor.create_stream()
        stream.accept_waveform(
            sample_rate=config.SAMPLE_RATE, waveform=pcm16.astype(np.float32) / 32768.0
        )
        stream.input_finished()
        if not self._extractor.is_ready(stream):
            return None
        v = np.asarray(self._extractor.compute(stream), dtype=np.float32)
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else None

    # --- runtime ---
    def process(self, pcm16: np.ndarray) -> float | None:
        """Similarity of this utterance to the enrolled voice (None = can't say).
        While enrolling, the utterance is added to the profile instead."""
        dur = len(pcm16) / config.SAMPLE_RATE
        if not self.available or dur < config.OWN_VOICE_MIN_UTT_S:
            return None
        emb = self.embed(pcm16)
        if emb is None:
            return None
        if self.enrolling:
            self._acc = emb * dur if self._acc is None else self._acc + emb * dur
            self._acc_seconds += dur
            if self._acc_seconds >= config.OWN_VOICE_ENROLL_S:
                self._finish_enrollment()
            return None
        if self.profile is None:
            return None
        return cosine(emb, self.profile)

    # --- enrolment ---
    def start_enrollment(self) -> None:
        self.enrolling = True
        self._acc, self._acc_seconds = None, 0.0
        log.info("own-voice enrolment started: %.0f s of speech needed", config.OWN_VOICE_ENROLL_S)

    def cancel_enrollment(self) -> None:
        self.enrolling = False

    def _finish_enrollment(self) -> None:
        v = self._acc / (np.linalg.norm(self._acc) + 1e-9)
        self.profile, self.profile_seconds = v.astype(np.float32), self._acc_seconds
        self.enrolling = False
        self._save_profile()
        log.info("own voice enrolled from %.1f s of speech", self.profile_seconds)

    def forget(self) -> None:
        self.profile, self.profile_seconds = None, 0.0
        PROFILE_PATH.unlink(missing_ok=True)

    # --- persistence ---
    def _save_profile(self) -> None:
        try:
            PROFILE_PATH.parent.mkdir(exist_ok=True)
            PROFILE_PATH.write_text(
                json.dumps(
                    {
                        "model": config.OWN_VOICE_MODEL.name,
                        "seconds": self.profile_seconds,
                        "embedding": [float(x) for x in self.profile],
                    }
                )
            )
        except OSError as e:
            log.warning("could not save voice profile: %s", e)

    def _load_profile(self) -> None:
        try:
            data = json.loads(PROFILE_PATH.read_text())
            if data.get("model") != config.OWN_VOICE_MODEL.name:
                return
            self.profile = np.asarray(data["embedding"], dtype=np.float32)
            self.profile_seconds = float(data.get("seconds", 0.0))
        except (OSError, ValueError, KeyError):
            pass

    def status(self) -> dict:
        return {
            "available": self.available,
            "reason": self.reason,
            "enrolled": self.profile is not None,
            "profile_seconds": self.profile_seconds,
            "enrolling": self.enrolling,
            "progress_s": self._acc_seconds if self.enrolling else 0.0,
            "target_s": config.OWN_VOICE_ENROLL_S,
            "threshold": config.OWN_VOICE_THRESHOLD,
        }
