#!/usr/bin/env bash
# Sona — Raspberry Pi 5 provisioning. Run from the repo root on the Pi:
#   bash pi/setup.sh
# Assumes Raspberry Pi OS Bookworm 64-bit (Lite is fine) and network access.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> apt packages"
sudo apt-get update
sudo apt-get install -y \
  git build-essential cmake \
  libsdl2-dev portaudio19-dev libportaudio2 \
  python3-venv python3-dev \
  fonts-dejavu-core bluez curl libusb-1.0-0 dfu-util

echo "==> user groups (serial + bluetooth)"
sudo usermod -aG dialout,bluetooth "$USER" || true

echo "==> whisper.cpp"
if [ ! -d sona_stt/whisper.cpp ]; then
  git clone https://github.com/ggml-org/whisper.cpp.git sona_stt/whisper.cpp
fi
cmake -S sona_stt/whisper.cpp -B sona_stt/whisper.cpp/build-pi \
  -DCMAKE_BUILD_TYPE=Release -DWHISPER_SDL2=ON
cmake --build sona_stt/whisper.cpp/build-pi -j"$(nproc)" \
  --target whisper-server whisper-cli whisper-stream

echo "==> whisper models (skipped if already copied with the repo)"
for m in base.en small.en; do
  if [ ! -f "sona_stt/whisper.cpp/models/ggml-$m.bin" ]; then
    sh sona_stt/whisper.cpp/models/download-ggml-model.sh "$m"
  fi
done

echo "==> yamnet model (skipped if already copied with the repo)"
mkdir -p models/yamnet
if [ ! -s models/yamnet/yamnet.tflite ]; then
  curl -sL -o models/yamnet/yamnet.tflite \
    "https://tfhub.dev/google/lite-model/yamnet/classification/tflite/1?lite-format=tflite"
fi
if [ ! -s models/yamnet/yamnet_class_map.csv ]; then
  curl -sL -o models/yamnet/yamnet_class_map.csv \
    "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv"
fi

echo "==> speaker-embedding model for own-voice recognition (skipped if present)"
mkdir -p models/speaker
if [ ! -s models/speaker/wespeaker_en_voxceleb_CAM++.onnx ]; then
  curl -sL -o models/speaker/wespeaker_en_voxceleb_CAM++.onnx \
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_CAM++.onnx"
fi

echo "==> ReSpeaker XVF3800 kit (firmware + xvf_host, from Seeed's GitHub)"
bash scripts/fetch_xvf_kit.sh

echo "==> python venv"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install ai-edge-litert || .venv/bin/pip install tflite-runtime

echo "==> selftest"
.venv/bin/python scripts/selftest.py || true

echo
echo "Done. Try:  .venv/bin/python -m sona.app --doa mock"
echo "Mirror UI:  http://<pi-ip>:8765   (open from any laptop on the same network)"
echo "Optional service: sudo cp pi/sona.service /etc/systemd/system/ && sudo systemctl enable --now sona"
