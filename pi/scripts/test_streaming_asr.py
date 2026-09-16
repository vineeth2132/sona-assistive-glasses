import queue
import sounddevice as sd
import numpy as np
import sherpa_onnx

DEVICE = 6
SAMPLE_RATE = 16000
CHANNEL_INDEX = 1

MODEL_DIR = "models/sherpa/sherpa-onnx-streaming-zipformer-en-2023-06-21"

recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
    tokens=f"{MODEL_DIR}/tokens.txt",
    encoder=f"{MODEL_DIR}/encoder-epoch-99-avg-1.int8.onnx",
    decoder=f"{MODEL_DIR}/decoder-epoch-99-avg-1.onnx",
    joiner=f"{MODEL_DIR}/joiner-epoch-99-avg-1.onnx",
    num_threads=4,
    sample_rate=SAMPLE_RATE,
    feature_dim=80,
    decoding_method="greedy_search",
)

stream = recognizer.create_stream()

audio_q = queue.Queue()


def callback(indata, frames, time, status):
    if status:
        print(status)

    audio_q.put(indata[:, CHANNEL_INDEX].copy())


print("Listening...")
print("Speak normally. Ctrl+C to stop.")
print()

last_text = ""

with sd.InputStream(
    device=DEVICE,
    channels=2,
    samplerate=SAMPLE_RATE,
    dtype="float32",
    blocksize=1600,
    callback=callback,
):
    try:
        while True:
            samples = audio_q.get()

            stream.accept_waveform(
                SAMPLE_RATE,
                samples,
            )

            while recognizer.is_ready(stream):
                recognizer.decode_stream(stream)

            text = recognizer.get_result(stream)

            if text and text != last_text:
                print("\r" + text + " " * 30, end="", flush=True)
                last_text = text

    except KeyboardInterrupt:
        print("\nStopped.")
