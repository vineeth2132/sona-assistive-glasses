#!/usr/bin/env bash
# Sona — bootstrap a fresh Mac (Apple Silicon). From the repo root:  bash scripts/setup_mac.sh
# Installs Homebrew deps, builds whisper.cpp, downloads the models (~1 GB), creates the venv,
# and runs the selftest. Safe to re-run: every step skips what is already there.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
echo "==> Homebrew packages"
brew install python@3.12 cmake sdl2 libusb dfu-util

echo "==> whisper.cpp (clone + build)"
[ -d sona_stt/whisper.cpp ] || git clone https://github.com/ggml-org/whisper.cpp.git sona_stt/whisper.cpp
cmake -S sona_stt/whisper.cpp -B sona_stt/whisper.cpp/build-mac \
  -DCMAKE_BUILD_TYPE=Release -DWHISPER_SDL2=ON > /dev/null
cmake --build sona_stt/whisper.cpp/build-mac -j"$(sysctl -n hw.ncpu)" \
  --target whisper-server whisper-cli whisper-stream | tail -1

echo "==> whisper models"
for m in base.en small.en; do
  [ -f "sona_stt/whisper.cpp/models/ggml-$m.bin" ] || sh sona_stt/whisper.cpp/models/download-ggml-model.sh "$m"
done

echo "==> YAMNet + speaker-embedding models"
mkdir -p models/yamnet models/speaker
[ -s models/yamnet/yamnet.tflite ] || curl -sL -o models/yamnet/yamnet.tflite \
  "https://tfhub.dev/google/lite-model/yamnet/classification/tflite/1?lite-format=tflite"
[ -s models/yamnet/yamnet_class_map.csv ] || curl -sL -o models/yamnet/yamnet_class_map.csv \
  "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv"
[ -s models/speaker/wespeaker_en_voxceleb_CAM++.onnx ] || curl -sL -o models/speaker/wespeaker_en_voxceleb_CAM++.onnx \
  "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_CAM++.onnx"

echo "==> ReSpeaker XVF3800 kit (firmware + xvf_host, from Seeed's GitHub)"
bash scripts/fetch_xvf_kit.sh

echo "==> Python venv"
[ -d .venv ] || /opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt ai-edge-litert ruff

echo "==> selftest"
.venv/bin/python scripts/selftest.py

echo
echo "Done.  Run:  .venv/bin/python -m sona.app    then open http://localhost:8765"
echo "Plug the reSpeaker into the USB-C port beside its 3.5 mm jack; the app picks it up automatically."
