# SONA — Sound-Oriented Navigation & Awareness

SONA is an assistive smart-glasses prototype for Deaf and hard-of-hearing users.

The system combines:

- live speech captions
- environmental sound detection
- direction-of-arrival estimation
- emergency sound alerts
- name-call detection
- directional visual awareness
- Even Realities G2 smart-glasses HUD

The main idea is:

```text
"What happened?"   → YAMNet / Whisper
"Where is it?"     → ReSpeaker XVF3800 DoA
"Show it to me"    → Even Realities G2
```

---

# 1. Repository Structure

This repository is a monorepo containing both the Raspberry Pi backend and the G2 frontend.

```text
sona-assistive-glasses/
│
├── README.md
├── .gitignore
│
├── pi/
│   │
│   ├── sona/
│   │   ├── app.py
│   │   ├── config.py
│   │   ├── state.py
│   │   ├── hub.py
│   │   │
│   │   ├── audio/
│   │   │   ├── capture.py
│   │   │   └── vad.py
│   │   │
│   │   ├── stt/
│   │   │   └── engine.py
│   │   │
│   │   ├── sounds/
│   │   │   ├── classifier.py
│   │   │   └── watchlist.py
│   │   │
│   │   ├── doa/
│   │   │   ├── xvf_usb.py
│   │   │   ├── xvf_serial.py
│   │   │   ├── gccphat.py
│   │   │   └── mock.py
│   │   │
│   │   ├── names/
│   │   │   ├── detector.py
│   │   │   └── matcher.py
│   │   │
│   │   ├── voice/
│   │   │   └── speaker.py
│   │   │
│   │   ├── display/
│   │   │   ├── mirror.py
│   │   │   ├── renderer.py
│   │   │   └── g1.py
│   │   │
│   │   └── summarize/
│   │
│   ├── scripts/
│   │   ├── selftest.py
│   │   ├── probe_hw.sh
│   │   ├── fetch_xvf_kit.sh
│   │   └── setup_mac.sh
│   │
│   ├── firmware/
│   ├── models/
│   ├── pi/
│   │   ├── setup.sh
│   │   ├── NOTES.md
│   │   └── sona.service
│   │
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── README.md
│
└── g2/
    ├── src/
    │   └── main.ts
    ├── public/
    ├── app.json
    ├── index.html
    ├── package.json
    ├── package-lock.json
    ├── tsconfig.json
    └── vite.config.ts
```

---

# 2. Current Hardware

## Raspberry Pi

Current development hardware:

```text
Raspberry Pi 5
4 GB RAM
64-bit Linux
```

The development Pi has also been tested on Debian 13 / Trixie.

The original setup script was written around Raspberry Pi OS Bookworm 64-bit, so package differences may occur between OS versions.

## Microphone Array

Current microphone:

```text
ReSpeaker XMOS XVF3800 4-Mic Array
USB VID:PID: 2886:001a
```

Firmware observed during development:

```text
XVF3800 firmware 2.1.0
ua-io16-sqr
```

The device provides:

- processed USB audio
- beamformed speech audio
- four microphones
- on-chip Direction of Arrival
- speech detection information

## Smart Glasses

Current display target:

```text
Even Realities G2
```

The G2 application is built using:

```text
@evenrealities/even_hub_sdk
```

The Pi does **not** directly drive the G2.

The data path is:

```text
Pi
 ↓
Wi-Fi / WebSocket
 ↓
Phone running Even Hub
 ↓
Even Realities G2
```

There is older G1-related code under:

```text
pi/sona/display/g1.py
```

but the current main development target is the **G2**.

---

# 3. Full System Architecture

```text
                   ┌──────────────────────────┐
                   │ ReSpeaker XVF3800 4-Mic │
                   └─────────────┬────────────┘
                                 │ USB
                                 ▼
                       ┌──────────────────┐
                       │ Raspberry Pi 5   │
                       └────────┬─────────┘
                                │
          ┌─────────────────────┼──────────────────────┐
          │                     │                      │
          ▼                     ▼                      ▼
   Audio Capture          XVF3800 DoA              YAMNet
          │                     │                      │
          ▼                     │                      │
         VAD                    │                      │
          │                     │                      │
          ▼                     │                      │
      Whisper STT               │                      │
          │                     │                      │
          ▼                     ▼                      ▼
      Captions             Direction             Sound Class
          │                     │                      │
          └─────────────────────┼──────────────────────┘
                                ▼
                         Shared UI State
                                │
                                ▼
                        WebSocket Server
                     ws://<PI-IP>:8765/ws
                                │
                                ▼
                         Even Hub Phone
                                │
                                ▼
                        Even Realities G2
                                │
                  ┌─────────────┴────────────┐
                  ▼                          ▼
             Live Captions            Direction HUD
                                      Sound Alerts
```

---

# 4. Main Processing Pipeline

The Raspberry Pi handles essentially all audio intelligence.

## Speech pipeline

```text
ReSpeaker
   ↓
16 kHz audio
   ↓
VAD
   ↓
utterance segmentation
   ↓
YAMNet speech confidence
   ↓
Whisper
   ↓
partial/final transcript
   ↓
direction gating
   ↓
WebSocket
   ↓
G2 caption
```

## Environmental sound pipeline

```text
ReSpeaker
   ↓
audio
   ↓
YAMNet
   ↓
watchlist matching
   ↓
HORN / SIREN / DOG / etc.
   ↓
XVF3800 sound direction
   ↓
UiState
   ↓
WebSocket
   ↓
G2 circular awareness HUD
```

## Direction pipeline

```text
XVF3800
   ↓
raw 0–359° bearing
   ↓
mounting correction
   ↓
SONA coordinate frame
   ↓
0°   = front
90°  = right
180° = behind
270° = left
   ↓
WebSocket
   ↓
G2 circular marker
```

---

# 5. Fresh Raspberry Pi Setup

Clone the repository directly on the Raspberry Pi.

```bash
git clone <REPOSITORY_URL>
cd sona-assistive-glasses/pi
```

Run:

```bash
bash pi/setup.sh
```

The setup script is designed to perform most of the provisioning automatically.

It installs packages including:

```text
git
build-essential
cmake
libsdl2-dev
portaudio
python3-venv
python3-dev
bluez
curl
libusb
dfu-util
```

It also:

```text
clones whisper.cpp
builds whisper.cpp
downloads Whisper models
downloads YAMNet
downloads the speaker-recognition model
fetches the XVF3800 support kit
creates the Python virtual environment
installs Python dependencies
runs the SONA self-test
```

---

# 6. Whisper Setup

`whisper.cpp` is intentionally **not committed to Git**.

It is downloaded during setup into:

```text
pi/sona_stt/whisper.cpp/
```

The Pi build is placed under:

```text
sona_stt/whisper.cpp/build-pi/
```

The executable used by SONA is typically:

```text
sona_stt/whisper.cpp/build-pi/bin/whisper-server
```

Do not copy this binary between architectures.

For example:

```text
Pi = ARM64 / aarch64
Typical laptop = x86_64
```

A Pi-built `whisper-server` executed on an x86 laptop will fail with:

```text
Exec format error
```

That is expected.

Build Whisper on the machine on which it will run.

### SDL2 note

During Pi development, SDL2 support was required for some whisper.cpp targets.

If the build fails around the stream/server components, configure with:

```bash
cmake \
  -S sona_stt/whisper.cpp \
  -B sona_stt/whisper.cpp/build-pi \
  -DCMAKE_BUILD_TYPE=Release \
  -DWHISPER_SDL2=ON
```

Then:

```bash
cmake --build sona_stt/whisper.cpp/build-pi \
  -j"$(nproc)" \
  --target whisper-server whisper-cli whisper-stream
```

---

# 7. Whisper Models

Large model binaries are NOT committed.

Examples:

```text
ggml-tiny.en.bin      ~75 MB
ggml-base.en.bin      ~142 MB
ggml-small.en.bin     ~466 MB
```

They are ignored by Git.

The current setup script automatically downloads:

```text
base.en
small.en
```

If using `tiny.en` for lower latency, download it manually:

```bash
cd sona_stt/whisper.cpp
sh models/download-ggml-model.sh tiny.en
```

The model will appear as:

```text
models/ggml-tiny.en.bin
```

Current Pi prototype usually runs:

```bash
.venv/bin/python -m sona.app \
  --mic-device 1 \
  --doa xvf \
  --model tiny.en
```

`tiny.en` is faster but less accurate.

`base.en` is more accurate but slower.

---

# 8. Python Environment

If not using the automated setup:

```bash
cd pi

python3 -m venv .venv

source .venv/bin/activate

pip install --upgrade pip

pip install -r requirements.txt
```

Some Raspberry Pi/Python combinations previously produced corrupted or unavailable packages through alternate package indexes.

If packages such as:

```text
soundfile
sounddevice
ai-edge-litert
```

behave strangely, force official PyPI:

```bash
pip install \
  --index-url https://pypi.org/simple \
  soundfile \
  sounddevice \
  ai-edge-litert
```

---

# 9. YAMNet

SONA uses YAMNet for environmental sound classification.

Model:

```text
models/yamnet/yamnet.tflite
```

Class map:

```text
models/yamnet/yamnet_class_map.csv
```

The model supports hundreds of AudioSet classes, but SONA currently only exposes configured watchlist targets.

Current default enabled labels:

```text
SIREN
HORN
DOORBELL
ALARM
DOG
```

These correspond to multiple underlying YAMNet classes.

For example:

```text
vehicle horn
air horn
train horn
car alarm
fire alarm
smoke detector
doorbell
ding-dong
bark
dog
siren
civil defense siren
```

The startup log may look like:

```text
YAMNet watching 19 classes for: ALARM, DOG, DOORBELL, HORN, SIREN
```

This does NOT mean YAMNet only knows 19 sounds.

It means SONA is currently watching 19 underlying AudioSet classes and grouping them into those configured labels.

---

# 10. Sound Detection Configuration

Main settings live in:

```text
pi/sona/config.py
```

Current repository defaults include approximately:

```python
SOUND_HOP_S = 0.5
SOUND_EMA_ALPHA = 0.6
SOUND_EVENT_TTL_S = 3.5
```

During prototype testing we also experimented with:

```python
SOUND_HOP_S = 0.25
SOUND_EMA_ALPHA = 0.75
```

and lower class thresholds to improve responsiveness.

Be careful when lowering thresholds because it can increase false positives.

Example prototype behavior:

```text
sound detected: HORN (0.31)
sound detected: ALARM (0.23)
```

If detections appear in the Pi terminal but not on the G2, then the problem is downstream of YAMNet:

```text
Pi state
→ WebSocket
→ G2 app
→ display
```

---

# 11. Audio Device Setup

The ReSpeaker currently appears as something similar to:

```text
reSpeaker XVF3800 4-Mic Array: USB Audio
```

Current working runtime has shown:

```text
hw:2,0
channel 2 of 2
16000 Hz
```

Device indices can change after reboot or when other USB audio devices are connected.

List Python audio devices with:

```bash
.venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"
```

Then select the appropriate index:

```bash
--mic-device <INDEX>
```

Example:

```bash
.venv/bin/python -m sona.app \
  --mic-device 1 \
  --doa xvf \
  --model tiny.en
```

---

# 12. Verify ReSpeaker USB

Check USB:

```bash
lsusb
```

Expected device:

```text
2886:001a
```

Check the XVF3800 interface:

```bash
.venv/bin/python -m sona.doa.xvf_usb
```

A working system has produced:

```text
XVF3800 connected: firmware 2.1.0
```

If USB works only with `sudo`, check USB permissions / udev configuration.

The normal final system should NOT require SONA to run as root.

---

# 13. Pi Power Check

Raspberry Pi undervoltage can cause strange USB/audio behavior.

Check:

```bash
vcgencmd get_throttled
```

Healthy result:

```text
throttled=0x0
```

We observed stable operation around:

```text
~54 °C
```

during normal testing.

---

# 14. Direction of Arrival

Direction comes from the XVF3800.

SONA's coordinate convention is:

```text
             0°
           FRONT

270° LEFT         RIGHT 90°

            BACK
             180°
```

In SONA:

```text
0°   = wearer front
90°  = wearer right
180° = behind wearer
270° = wearer left
```

The XVF3800 raw convention uses the connector/cable edge as its reference.

Current mounting assumption:

```text
board component side up
USB/cable edge toward the BACK of the wearer
```

Therefore the current configuration uses:

```python
XVF_DOA_SIGN = 1
AZIMUTH_OFFSET_DEG = 180.0
```

Transformation:

```text
sona_angle =
    (XVF_DOA_SIGN * raw_angle + AZIMUTH_OFFSET_DEG) % 360
```

Physical calibration is still important.

Test:

```text
sound directly in front
sound directly right
sound directly behind
sound directly left
```

Expected approximate readings:

```text
front  →   0°
right  →  90°
back   → 180°
left   → 270°
```

Adjust `AZIMUTH_OFFSET_DEG` if required.

If left/right are mirrored, investigate:

```python
XVF_DOA_SIGN = -1
```

---

# 15. Voice Activity Detection

The audio stream is divided into small frames.

Current configuration includes:

```python
SAMPLE_RATE = 16000
FRAME_MS = 30
```

VAD determines when speech starts and stops.

Important settings include:

```python
VAD_AGGRESSIVENESS
VAD_TRIGGER_RATIO
VAD_TRIGGER_WINDOW_MS
VAD_END_SILENCE_MS
UTTERANCE_MAX_S
UTTERANCE_MIN_S
```

Current end-silence is approximately:

```text
450 ms
```

This affects caption latency.

Reducing it can make captions finish faster but may split normal sentences too aggressively.

---

# 16. Live Caption Pipeline

The current caption pipeline is:

```text
microphone
   ↓
VAD
   ↓
speech segment
   ↓
speech confidence
   ↓
Whisper
   ↓
partial transcript
   ↓
final transcript
   ↓
mode/direction gating
   ↓
UiState
   ↓
WebSocket
   ↓
G2
```

Partial STT currently exists.

Relevant settings:

```python
STT_PARTIALS = True
STT_PARTIAL_INTERVAL = 1.0
STT_PARTIAL_MIN_S = 1.0
```

This means an in-progress utterance can be periodically re-transcribed.

---

# 17. Current Live Caption Problem

This is an active development area.

Current observed issues:

```text
caption latency is still too high
tiny.en occasionally produces incorrect/gibberish text
Whisper occasionally hallucinates generic phrases
partial caption processing may lag
```

Examples previously observed include unwanted phrases such as:

```text
Thanks for watching today.
Thank you.
```

even when the real speech was different.

There is already a speech-confidence gate using YAMNet to reduce Whisper hallucinations.

Relevant settings include:

```python
SPEECH_GATE_MIN
SPEECH_GATE_SUSPECT
```

The current backend-development branch should focus on:

```text
lower caption latency
better VAD segmentation
better partial transcript behavior
gibberish/hallucination filtering
model selection
avoiding unnecessary reprocessing
```

---

# 18. Caption Modes

SONA currently supports three modes.

## Surround

```text
captions from all directions
environmental alerts enabled
```

## Focus

```text
captions only inside the front listening cone
environmental alerts still work from all directions
```

Default focus cone:

```text
60°
```

Equivalent to approximately:

```text
±30° from front
```

## Alerts

```text
normal captions hidden
important environmental sounds shown
name calls shown
```

This is why logs may say:

```text
hidden in alerts mode
```

or:

```text
hidden in focus mode
```

That does NOT mean Whisper failed.

It means the transcript was intentionally gated by the current UI mode.

---

# 19. Name Detection

The system supports detecting when somebody calls the wearer's name.

Current development name has been configured as:

```text
vineth
```

Name detection receives Whisper text and performs fuzzy/phonetic matching.

A name alert also attempts to attach the recent talker direction.

Example conceptual state:

```json
{
  "name_alert": "vineth",
  "name_angle": 120
}
```

---

# 20. Own-Voice Recognition

The project contains speaker verification support.

Model:

```text
wespeaker_en_voxceleb_CAM++.onnx
```

Goal:

```text
identify the wearer's own voice
optionally suppress their own captions
```

Current prototype often starts with:

```text
own-voice recognition ready
not enrolled
ignore=False
```

Own-voice filtering is therefore usually disabled while debugging.

---

# 21. Pi Runtime

Main command:

```bash
cd pi
```

Then:

```bash
.venv/bin/python -m sona.app \
  --mic-device 1 \
  --doa xvf \
  --model tiny.en
```

A healthy startup should contain lines similar to:

```text
own-voice recognition ready
mirror running at http://localhost:8765
whisper-server ready
YAMNet watching ...
name detector watching ...
sona is up
microphone: reSpeaker XVF3800 ...
XVF3800 connected ...
```

---

# 22. Running Without Real DoA Hardware

For development without the ReSpeaker DoA:

```bash
.venv/bin/python -m sona.app \
  --doa sweep \
  --model tiny.en
```

There is also a mock DoA implementation.

This is useful for frontend/UI development.

---

# 23. Mirror UI

The Pi provides a browser mirror at:

```text
http://<PI_IP>:8765
```

Example:

```text
http://10.x.x.x:8765
```

The mirror is useful for:

```text
checking captions
checking sound detections
checking direction
changing modes/settings
debugging without glasses
```

The WebSocket endpoint is:

```text
ws://<PI_IP>:8765/ws
```

---

# 24. WebSocket Protocol

The G2 should communicate with the Pi through this interface instead of directly touching the audio/STT code.

Typical frame:

```json
{
  "type": "frame",
  "state": {
    "mode": "surround",
    "cone": 60,

    "angle": 120,
    "doa_active": true,
    "doa_speech": false,

    "partial": "hello how are...",

    "sound": "HORN",
    "sound_angle": 95,
    "sound_score": 0.42,

    "name_alert": null,
    "name_angle": null,

    "history": [
      {
        "text": "Hello how are you?",
        "angle": 120,
        "shown": true,
        "me": null,
        "own": false
      }
    ]
  }
}
```

Important fields:

```text
state.mode
state.cone
state.angle
state.doa_active
state.partial
state.sound
state.sound_angle
state.sound_score
state.name_alert
state.name_angle
state.history
```

Frontend code should depend on these fields rather than importing backend internals.

---

# 25. WebSocket Commands From G2

Mode change:

```json
{
  "type": "mode",
  "value": "surround"
}
```

Possible values:

```text
surround
focus
alerts
```

Other mirror commands exist for:

```text
cone adjustment
sound watchlist control
name configuration
own-voice enrollment
```

---

# 26. Finding the Raspberry Pi IP

On the Pi:

```bash
hostname -I
```

or:

```bash
ip addr
```

Use that IP for the G2 WebSocket.

Example:

```ts
const PI_WS =
  'ws://192.168.x.x:8765/ws'
```

The phone, laptop, and Pi must be able to reach each other over the network.

---

# 27. G2 Setup

On the development laptop:

```bash
cd g2
npm install
```

Then:

```bash
npm run dev
```

Vite should expose something similar to:

```text
http://<LAPTOP_IP>:5173
```

Find laptop IP:

```bash
hostname -I
```

---

# 28. G2 `vite.config.ts`

The development server must be reachable from the phone.

Example:

```ts
import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    host: true,

    hmr: {
      host: '<LAPTOP_IP>',
    },
  },
})
```

Replace:

```text
<LAPTOP_IP>
```

with the laptop's Wi-Fi IP.

Do NOT commit a random developer's IP as a permanent project assumption.

---

# 29. G2 `app.json`

The G2 app requires network permission to reach the Pi.

Example:

```json
{
  "package_id": "com.example.evenhubminimal",
  "edition": "202601",
  "name": "Sona G2",
  "version": "0.1.0",
  "min_app_version": "2.0.0",
  "min_sdk_version": "0.0.10",
  "entrypoint": "index.html",

  "permissions": [
    {
      "name": "network",
      "desc": "Connect to the Sona Raspberry Pi",
      "whitelist": [
        "ws://<PI_IP>:8765"
      ]
    }
  ],

  "supported_languages": [
    "en"
  ]
}
```

Replace:

```text
<PI_IP>
```

with the actual Pi address.

---

# 30. Launching the G2 App

Start Vite:

```bash
cd g2
npm run dev
```

Generate the Even Hub QR:

```bash
npx evenhub qr \
  --clear \
  --url "http://<LAPTOP_IP>:5173"
```

Scan the QR from the Even Hub development/prototype interface.

When container layout or permissions change, it is often safer to:

```text
exit Prototype Mode
restart Vite
scan the QR again
```

rather than relying entirely on hot reload.

---

# 31. G2 Display Characteristics

G2 display resolution:

```text
576 × 288
```

The display uses grayscale levels rendered as green on the glasses.

Image containers have limited size and image transmission is significantly slower than simple text updates.

Bitmap updates can take roughly:

```text
~0.5–2 seconds
```

depending on payload/link conditions.

Therefore:

**Do not treat G2 bitmap rendering like a 30/60 FPS display.**

Avoid:

```text
setInterval(..., 100 ms)
continuous image animation
unbounded bitmap queues
```

---

# 32. Current G2 Direction HUD Strategy

The current UI uses a circular directional awareness indicator.

Conceptually:

```text
              FRONT

             ▲
        ╭──────────╮
       ╱            ╲
      │              ●  ← detected direction
      │    HORN      │
      │              │
       ╲            ╱
        ╰──────────╯
```

The system separates:

```text
WHERE → marker around circle

WHAT  → sound class in/near circle
```

Direction is quantized into sectors to reduce bitmap traffic.

Current prototype uses approximately:

```text
30° sectors
```

That gives:

```text
12 possible displayed directions
```

instead of generating a new bitmap for every 1° change.

---

# 33. Latest-Wins Bitmap Strategy

A previous implementation queued every direction update.

That caused:

```text
old frame
old frame
old frame
old frame
new frame
```

to accumulate because the glasses could not transfer images as quickly as the Pi generated state changes.

The corrected strategy is:

```text
90°
91°
94°
120°
121°

↓ keep only latest

120°/121°
```

Only the newest pending radar state is transmitted.

This is called a:

```text
latest-wins queue
```

There should never be a huge bitmap backlog.

---

# 34. Sound Display Hold

Sound classifiers may rapidly produce:

```text
HORN
ALARM
HORN
```

within a short period.

Because G2 bitmap transfer is slow, a label can disappear before the wearer actually sees it.

The current frontend prototype therefore uses a short hold/latch.

Approximately:

```text
SOUND_HOLD_MS = 3000
```

A sound remains visible for around three seconds.

A weaker different classification should not immediately replace a stronger active detection.

This behavior is part of the frontend prototype and may still require tuning.

---

# 35. Current G2 UI Status

Working or mostly working:

```text
Pi → phone WebSocket connection
direction data
circular direction marker
mode switching
captions from WebSocket
sound events arriving from Pi
```

Still under active development:

```text
environmental sound label presentation
best HUD layout
sound animation/graphics
caption layout
connection handling
display refresh optimization
```

Do not assume the current UI is production-ready.

---

# 36. Current Backend Status

Working or mostly working:

```text
ReSpeaker audio
XVF3800 USB control
XVF3800 DoA
YAMNet
Whisper
name detection
mirror server
WebSocket
Focus / Surround / Alerts modes
```

Active backend work:

```text
live caption latency
caption accuracy
Whisper gibberish
hallucination filtering
partial transcript behavior
VAD tuning
```

---

# 37. Team Development Split

There are currently two main development tracks.

## Backend / Live Captions

Primary branch:

```text
feature/live-captions
```

Primary ownership:

```text
pi/sona/audio/
pi/sona/stt/
pi/sona/config.py
caption-related parts of pi/sona/app.py
```

Focus:

```text
Whisper latency
partial captions
VAD
hallucination filtering
gibberish filtering
speech confidence
model benchmarking
```

Avoid unnecessary G2 UI changes from this branch.

---

## G2 UI / Connectivity

Primary branch:

```text
feature/g2-ui
```

Primary ownership:

```text
g2/
```

Focus:

```text
G2 HUD
radar
sound labels
caption layout
interaction
connection/reconnection
Even Hub integration
performance
```

Avoid changing Whisper/VAD/backend behavior unless coordinated.

---

# 38. Shared Interface Ownership

The main shared backend/frontend boundary is:

```text
pi/sona/display/mirror.py
```

This file defines the WebSocket payload consumed by the G2.

Do not casually modify field names.

For example, changing:

```json
"sound_angle"
```

to:

```json
"soundDirection"
```

would break frontend code.

Protocol changes should be discussed before merging.

---

# 39. Git Workflow

Do not both work directly on `main`.

Start by syncing:

```bash
git checkout main
git pull
```

Backend developer:

```bash
git checkout -b feature/live-captions
```

Frontend developer:

```bash
git checkout -b feature/g2-ui
```

---

# 40. Backend Commits

Example:

```bash
git add \
  pi/sona/stt \
  pi/sona/audio \
  pi/sona/config.py \
  pi/sona/app.py

git commit -m "Improve live caption latency and filtering"

git push -u origin feature/live-captions
```

---

# 41. Frontend Commits

Example:

```bash
git add g2/

git commit -m "Improve G2 directional HUD"

git push -u origin feature/g2-ui
```

Merge changes through Pull Requests.

Target:

```text
main
```

---

# 42. Before Merging Backend Changes

Run:

```bash
cd pi
```

Lint:

```bash
.venv/bin/ruff check sona scripts
```

Quick self-test:

```bash
.venv/bin/python scripts/selftest.py --quick
```

Also manually verify startup if hardware is available.

---

# 43. Before Merging Frontend Changes

Run:

```bash
cd g2
npm install
npm run dev
```

Check browser console for:

```text
WebSocket errors
image conversion errors
duplicate connections
unbounded radar sends
```

Verify on the actual G2 when possible.

---

# 44. Git Ignore Policy

Do NOT commit generated, machine-specific, or large files.

Examples:

```text
.venv/
node_modules/
dist/
out/
__pycache__/
whisper.cpp build output
Whisper .bin models
YAMNet .tflite model
speaker .onnx model
runtime logs
developer-specific environment files
```

Large models are recreated by setup scripts.

---

# 45. Why Models Are Not in Git

Examples:

```text
tiny.en   ~75 MB
base.en   ~142 MB
small.en  ~466 MB
```

They make the repository unnecessarily large and some exceed normal GitHub file-size limits.

Models should be downloaded during setup instead.

---

# 46. Verify Large Files Before Commit

From repository root:

```bash
find . \
  -type f \
  -size +50M \
  -exec ls -lh {} \;
```

Then check whether Git actually tracks any Whisper models:

```bash
git ls-files | grep 'ggml-.*\.bin'
```

Expected:

```text
(no output)
```

---

# 47. Check Git Status

Before every push:

```bash
git status
```

Make sure you are not accidentally committing:

```text
.venv
node_modules
models
private keys
.pem files
Wi-Fi credentials
logs
```

---

# 48. Network Requirements

During development:

```text
Pi
laptop
phone
```

should normally be on networks where they can reach each other.

The phone must be able to reach:

```text
Pi:8765
```

and the phone must also be able to reach:

```text
Laptop:5173
```

for Vite development.

University/captive-portal networks may block peer-to-peer traffic.

During development, a phone hotspot was often more reliable.

---

# 49. University Wi-Fi Notes

Captive portal networks can create problems for headless Raspberry Pi devices.

Issues previously encountered included:

```text
UTUM Guest captive portal
slow downloads
Pi unable to reach login page
```

A hotspot worked as a temporary solution.

Eduroam was later configured.

Network configuration is machine/institution-specific and Wi-Fi credentials must never be committed to Git.

---

# 50. Mirror Clients

The Pi logs WebSocket connections:

```text
mirror client connected (1 total)
mirror client connected (2 total)
```

A few clients can be normal:

```text
browser mirror
phone
G2/Vite instance
```

A continuously increasing number such as:

```text
10
20
50
100
```

indicates a reconnect/client leak.

The G2 frontend should maintain one WebSocket and avoid creating duplicate connections during hot reload.

---

# 51. Common Error — Port 8765 Already Used

If SONA reports the mirror port is already in use:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

Make sure an older SONA process is not still running.

Do not run two backend instances at the same time unless intentionally using separate ports.

---

# 52. Common Error — Exec Format Error

Example:

```text
OSError: [Errno 8] Exec format error:
whisper-server
```

Cause:

```text
binary compiled for a different CPU architecture
```

Example:

```text
Pi ARM binary copied to x86 laptop
```

Fix:

```text
rebuild whisper.cpp locally
```

Do not commit compiled Whisper binaries.

---

# 53. Common Error — No Sound Labels on G2

First inspect the Pi terminal.

If it says:

```text
sound detected: HORN
```

then classification is working.

The problem is likely:

```text
mirror payload
WebSocket
frontend state
G2 rendering
```

If there is no:

```text
sound detected:
```

line at all, investigate:

```text
audio input
YAMNet
watchlist
threshold
classifier
```

Debug backend and frontend separately.

---

# 54. Common Error — Direction Works but Classification Does Not

Direction and classification are independent pipelines.

Direction:

```text
XVF3800 → DoA
```

Classification:

```text
audio → YAMNet
```

Therefore:

```text
direction working
```

does NOT prove:

```text
YAMNet working
```

and vice versa.

---

# 55. Common Error — Captions Hidden

Logs like:

```text
hidden in focus mode
```

or:

```text
hidden in alerts mode
```

are expected when the mode intentionally blocks that caption.

Switch to:

```text
SURROUND
```

when debugging STT itself.

---

# 56. Focus Mode

Focus mode uses direction gating.

Example:

```text
FOCUS 60°
```

means roughly:

```text
±30° around the wearer's front
```

Environmental alerts still need to be available from outside the focus cone.

---

# 57. G2 Gestures

Current prototype behavior:

```text
single tap
    ↓
cycle mode

SURROUND
→ FOCUS
→ ALERTS
→ SURROUND
```

Double tap:

```text
exit/shutdown app page
```

This behavior lives in:

```text
g2/src/main.ts
```

---

# 58. Current Development Priorities

## Backend priority

Improve live caption quality:

```text
lower end-to-end latency
reduce gibberish
reduce hallucinations
improve partial captions
benchmark tiny.en vs base.en
improve VAD timing
avoid unnecessary Whisper calls
```

## Frontend priority

Improve G2 UX:

```text
clear sound identity
clear direction
low bitmap traffic
readable captions
stable connection
clean mode indication
```

---

# 59. Product Goal

The intended behavior is:

```text
Person speaking nearby
        ↓
caption appears

Horn on the right
        ↓
HORN shown
direction indicator appears on right

Siren behind
        ↓
SIREN shown
direction indicator appears behind

Wearer's name called
        ↓
name alert
speaker direction indicated
```

The wearer should not need to look at or interact heavily with a phone.

The phone primarily acts as the bridge between the Pi backend and G2.

---

# 60. Prototype Philosophy

Keep compute-heavy processing on the Raspberry Pi:

```text
Whisper
YAMNet
DoA
audio processing
```

Keep G2 responsible mainly for:

```text
presentation
interaction
connection state
```

This separation allows backend and frontend development to proceed independently.

---

# 61. Fresh Teammate Setup Summary

## Raspberry Pi developer

```bash
git clone <REPOSITORY_URL>

cd sona-assistive-glasses/pi

bash pi/setup.sh
```

If using tiny.en:

```bash
cd sona_stt/whisper.cpp

sh models/download-ggml-model.sh tiny.en

cd ../..
```

Then:

```bash
.venv/bin/python -m sona.app \
  --mic-device 1 \
  --doa xvf \
  --model tiny.en
```

Find Pi IP:

```bash
hostname -I
```

Test mirror:

```text
http://<PI_IP>:8765
```

---

## G2 developer

```bash
git clone <REPOSITORY_URL>

cd sona-assistive-glasses/g2

npm install
```

Update:

```text
app.json
vite.config.ts
src/main.ts PI websocket address
```

with the current Pi/laptop IP addresses.

Then:

```bash
npm run dev
```

Generate QR:

```bash
npx evenhub qr \
  --clear \
  --url "http://<LAPTOP_IP>:5173"
```

Open the app through Even Hub and test on G2.

---

# 62. Current Development Branches

Backend:

```text
feature/live-captions
```

Frontend:

```text
feature/g2-ui
```

Stable integration:

```text
main
```

---

# 63. Important Rule

Before changing the Pi ↔ G2 message format:

**coordinate with the other developer first.**

The WebSocket protocol is the contract that allows the backend and frontend to be developed independently.

---

# 64. Project Status

This is currently a research/prototype system.

It is not a medical device and should not currently be relied upon as the only safety mechanism for detecting hazards.

Current functionality and performance are still being tested and improved.

---

# 65. Quick Reference

Start Pi:

```bash
cd pi

.venv/bin/python -m sona.app \
  --mic-device 1 \
  --doa xvf \
  --model tiny.en
```

Start G2 development server:

```bash
cd g2
npm run dev
```

Pi mirror:

```text
http://<PI_IP>:8765
```

WebSocket:

```text
ws://<PI_IP>:8765/ws
```

Direction:

```text
0° front
90° right
180° back
270° left
```

Branches:

```text
feature/live-captions
feature/g2-ui
main
```

---

# Contributors

SONA is being developed collaboratively as an assistive wearable prototype.

Current work is split between:

```text
Raspberry Pi / audio / STT / perception

and

Even Realities G2 / UI / connectivity
```