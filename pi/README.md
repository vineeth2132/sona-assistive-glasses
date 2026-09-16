# Sona — sound awareness glasses for Deaf / Hard-of-Hearing people

Live captions + sound direction + sound identification, rendered on Even Realities G1
AR glasses (used as a dumb BLE display). Brain: Raspberry Pi 5 (dev on Mac — same code).

```
Mic / ReSpeaker ──► frames ──► VAD ──► whisper.cpp ──► captions ─┐
                      │                                          ├─► UiState ─► Renderer ─► web mirror (:8765)
                      └────► YAMNet (sound class) ──► events ────┤                    └───► G1 glasses (BLE)
ESP32 / GCC-PHAT ────────────► direction of arrival ─────────────┘
```

## Setup on a fresh Mac (Apple Silicon)

```bash
git clone <this repo> sona_glasses && cd sona_glasses
bash scripts/setup_mac.sh        # Homebrew deps, whisper.cpp build, models (~1 GB), venv, selftest
.venv/bin/python -m sona.app     # then open http://localhost:8765
```

Raspberry Pi: `bash pi/setup.sh`, playbook in [pi/NOTES.md](pi/NOTES.md). Models, whisper.cpp
and your local settings/voice profile (`out/`) are not in git — the setup scripts fetch or
create them. Seeed's XVF3800 firmware images and `xvf_host` tools are fetched from their
public GitHub repo by `scripts/fetch_xvf_kit.sh` (run by the setup scripts) — their repo has no
license, so we don't redistribute the binaries.

## Quickstart (Mac)

```bash
.venv/bin/python scripts/selftest.py          # renderer + yamnet + whisper, no mic needed
.venv/bin/python -m sona.app                  # live: mic + mock DoA
# then open http://localhost:8765  ← the mirror = dev simulator = projector view
```

Useful flags (`python -m sona.app --help`):
`--wav file.wav` replay audio · `--doa sweep|serial|gccphat` · `--g1` real glasses ·
`--g1-bmp` bitmap mode · `--model small.en` · `--name Miquel` · `--no-stt` / `--no-sounds`

In the mirror page you can: drag the compass (fake sound direction), fire test
sound events, set your name and simulate someone calling it, type fake captions,
switch modes — all without any hardware.

## Modes (buttons in the mirror; a physical button later)

- **Focus** — captions only from an adjustable cone in front (40/60/90/180°), decided by the
  bearing of each utterance; name-calls and important sounds still alert from anywhere.
- **Surround** — captions from everywhere + alerts.
- **Alerts only** — no captions; name-calls + important sounds only.

## Own voice

The wearer enrols once in the mirror (**MY VOICE → ENROLL**, ~20 s of natural speech, nobody
else talking); each utterance is then compared to that voice profile (speaker embeddings,
sherpa-onnx + WeSpeaker CAM++). With **hide my own words** on, the wearer's utterances are
not transcribed or shown. The HEARD log tags every utterance with `me 0.xx` so the
threshold (`OWN_VOICE_THRESHOLD`) can be tuned against real people.

## Three features

1. **Captions** — mic → VAD → whisper.cpp. Shown as *pop-on* pages, the way live
   CART captioning works: rows fill from the top down and never move once written;
   when a sentence doesn't fit, the page clears and it starts at the top; ~6 s of
   silence clears the page. In-progress speech shows live with a trailing `…`.
   No direction needed (you face the speaker); a YAMNet speech-score gate drops
   Whisper's noise hallucinations. Tunables: `CAPTION_*` in `sona/config.py`.
2. **Sound awareness** — YAMNet flags important sounds (siren, horn, doorbell, baby…)
   and the compass ring shows their direction with the label inside.
3. **Name call** — when someone says the wearer's name (phonetic match, so Whisper
   mis-spellings still count), a bold alert points to the caller using the mic array's
   speech direction. Straight from the DHH interviews: missing your name being called
   was the most-cited frustration. Set via `--name` or the mirror.

## Layout

- `sona/` — the app (see module docstrings): `audio/` capture+VAD, `stt/` whisper server
  client, `sounds/` YAMNet classifier, `doa/` direction sources (mock / ESP32 serial /
  GCC-PHAT), `display/` renderer + G1 BLE driver + web mirror, `app.py` orchestrator.
- `sona_stt/whisper.cpp` — vendored whisper.cpp (own git repo, ignored here).
- `models/` — YAMNet tflite + class map (whisper models live in whisper.cpp/models).
- `pi/` — SD-card provisioning (`setup.sh`), hardware-day playbook (`NOTES.md`), systemd unit.
- `firmware/esp32_doa/` — XIAO ESP32S3 sketch: XVF3800 DoA → USB serial.

## Hardware day

Follow [pi/NOTES.md](pi/NOTES.md) top to bottom: flash SD → rsync repo → `bash pi/setup.sh`
→ STT benchmark → ReSpeaker path A/B → G1 pairing (from the Mac first).

## Glasses protocol notes

Text mode (fast, firmware-rendered, ~40 chars × 5 lines) is the default; bitmap mode
(576×136 1-bit, ~1 s/frame over BLE) is `--g1-bmp`. The Even phone app must be
disconnected while Sona drives the glasses. Protocol refs in `sona/display/g1.py`.
