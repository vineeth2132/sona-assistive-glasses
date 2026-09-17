import logging
from pathlib import Path

import numpy as np
import sherpa_onnx

from .. import config

log = logging.getLogger(__name__)


class SherpaStreamingSTT:
    def __init__(self):
        model = (
            config.MODELS_DIR
            / "sherpa-onnx-streaming-zipformer-en-2023-06-21"
        )

        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(model / "tokens.txt"),
            encoder=str(model / "encoder-epoch-99-avg-1.int8.onnx"),
            decoder=str(model / "decoder-epoch-99-avg-1.onnx"),
            joiner=str(model / "joiner-epoch-99-avg-1.int8.onnx"),
            num_threads=2,
            sample_rate=config.SAMPLE_RATE,
            feature_dim=80,
            decoding_method="greedy_search",
            enable_endpoint_detection=False,
        )

        self.stream = None
        log.info("Sherpa streaming STT ready")

    def start_utterance(self):
        self.stream = self.recognizer.create_stream()

    def feed(self, pcm16: np.ndarray) -> str:
        if self.stream is None:
            self.start_utterance()

        samples = pcm16.astype(np.float32) / 32768.0

        self.stream.accept_waveform(
            config.SAMPLE_RATE,
            samples,
        )

        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)

        return self.recognizer.get_result(self.stream).strip()

    def finish(self) -> str:
        if self.stream is None:
            return ""

        self.stream.input_finished()

        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)

        text = self.recognizer.get_result(self.stream).strip()

        self.stream = None

        return text
