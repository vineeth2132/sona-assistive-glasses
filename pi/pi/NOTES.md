# Hardware playbook (everything happens today — 2026-09-14)

## 1. Flash the SD card (on the Mac)
- Raspberry Pi Imager → **Raspberry Pi OS Lite (64-bit), Bookworm** → 64 GB card.
- In Imager settings (gear icon): hostname `sona`, user `sona`, enable **SSH**,
  add the Wi-Fi credentials (use a phone hotspot as backup network — venue Wi-Fi
  often blocks device-to-device traffic).
- Boot the Pi, then from the Mac: `ssh sona@sona.local`.

## 2. Get the repo + models onto the Pi
Fastest offline path: copy the whole `sona_glasses` folder to the SD card's boot
partition or over the network:
```
rsync -av --exclude .venv --exclude out --exclude sona_stt/whisper.cpp/build-mac \
  ~/Documents/sona_glasses/ sona@sona.local:~/sona_glasses/
```
(This carries the whisper + yamnet models, so the Pi needs internet only for apt/pip.)
Then on the Pi: `cd ~/sona_glasses && bash pi/setup.sh`

## 3. Pi 5 power
- Pi 5 wants a 5V/5A USB-PD supply. On a 3A power bank it boots with reduced
  USB-port current — our peripherals (BLE + mic array) are light, so it usually
  works. If USB devices misbehave, add to `/boot/firmware/config.txt`:
  `usb_max_current_enable=1` — and get a PD bank that supports the 5V/5A profile.
- Fit the active cooler if there is one; whisper pins all 4 cores.

## 4. STT benchmark (decides base.en vs small.en)
```
cd ~/sona_glasses/sona_stt/whisper.cpp
./build-pi/bin/whisper-cli -m models/ggml-base.en.bin  -f samples/jfk.wav -t 4
./build-pi/bin/whisper-cli -m models/ggml-small.en.bin -f samples/jfk.wav -t 4
```
Rule of thumb: keep whichever transcribes the 11 s clip in ≲4 s. Set the winner in
`sona/config.py` (`STT_MODEL`).

## 5. ReSpeaker XVF3800 (XIAO ESP32S3 variant) — Path A, verified on the Mac 2026-09-14
The board has **two USB-C ports. Use the XMOS port — the one beside the 3.5 mm jack.**
(The other port is the XIAO ESP32S3; it enumerates as an Espressif JTAG/serial device.)
The shipped I2S firmware is silent on USB, so flash the USB firmware once:
1. Unplug. Hold **MUTE**, plug in while holding, keep holding until the **red LED blinks**.
2. `dfu-util -l` must list `[2886:001a] ... "reSpeaker DFU Upgrade"` (`sudo` on the Pi).
3. `dfu-util -R -e -a 1 -D firmware/xvf3800/respeaker_xvf3800_usb_dfu_firmware_v2.1.0_16k6ch.bin`
4. Re-plug normally. `scripts/probe_hw.sh` → a 6-channel, 16 kHz "reSpeaker XVF3800" input:
   ch1 = processed conference output · ch2 = ASR output of the auto-selected beam (→ STT)
   ch3–ch6 = raw microphones 0–3 (→ `--doa gccphat`).
5. `.venv/bin/python -m sona.doa.xvf_usb` → prints firmware, build profile, mic geometry
   and streams `DOA_VALUE` (0–359 + speech flag). Then run the app with `--doa xvf`.
6. Angle mapping (set 2026-09-14 on the bench): the board's 0° is its cable edge; worn with
   the cable at the back of the head that is Sona's 180°, so `AZIMUTH_OFFSET_DEG = 180`,
   `XVF_DOA_SIGN = +1`. Check on the hat: clap in front → dot at the top; clap at the
   wearer's right → dot on the right. If left/right are mirrored, set `XVF_DOA_SIGN = -1`.

Fallback (Path B): stock I2S firmware + `firmware/esp32_doa/` sketch → `--doa serial`.
Tools: `tools/xvf_host/{mac_arm64,rpi_64bit}/xvf_host` (e.g. `xvf_host AEC_AZIMUTH_VALUES`).
Revert to I2S: flash `firmware/xvf3800/respeaker_xvf3800_i2s_dfu_firmware_v1.0.7.bin` the same way.

**Two DoA roles (decided with Miquel 2026-09-14):**
- **Speech direction → the name-call feature.** The XVF3800's on-chip DoA is
  *speech-tuned*, which is exactly what we want for "who just called my name."
  Path B's serial stream (or Path A on-chip DoA) feeds this. We do NOT need
  precise direction for normal captions — you face the person you talk to.
- **Any-sound direction → important sounds (siren/horn/baby).** On-chip DoA may
  ignore non-speech, so use `--doa gccphat` on raw mic channels (Path A) for these.
- Ideal setup exposes both; if we can only pick one on the day, prioritise whatever
  makes the **name-call direction** solid — that was the strongest interview signal.

## 6. G1 glasses bring-up (do this from the MAC first — faster iteration)
- Charge them; make sure the **Even phone app is fully closed / Bluetooth off on
  the phone** — the glasses accept one host at a time.
- `python -m sona.app --g1` → scans for `..._L_...` / `..._R_...` devices, connects
  both arms, caches addresses in `pi/g1_addresses.json`.
- Verify: captions appear in text mode; then measure bitmap rate with `--g1-bmp`
  and set `G1_BMP_MIN_INTERVAL` (and possibly `G1_SCREEN_STATUS = 0x71`) in config.
- Repeat on the Pi (BlueZ). If scanning is flaky: `bluetoothctl` → `scan on` to
  confirm the arms advertise.

## 7. Name-call feature (someone calls the wearer's name)
- Set the name in the mirror ("YOUR NAME") or with `--name Miquel` (comma-separate
  several). Detection runs on the live transcript with phonetic matching, so
  Whisper spelling it "Michael"/"Miguel" still fires. Direction comes from the
  speech-DoA buffered at the moment the name was heard → shown with a bold wedge.
- Bench test: have someone stand out of the wearer's view and call the name; confirm
  (a) the alert fires and (b) the wedge points the right way. Tune in `config.py`:
  `NAME_MATCH_RATIO` / `NAME_SOUNDEX_RATIO` (recall vs false alarms),
  `NAME_ALERT_TTL_S`, `NAME_COOLDOWN_S`, `NAME_DOA_WINDOW_S`.
- **Known limit:** transcript-based detection inherits Whisper's ~1–2 s latency and
  its far-field weakness (a name shouted from 4 m in noise may not transcribe).
  **Upgrade path if it underperforms on the day:** add always-on keyword spotting
  for the specific demo name — openWakeWord (open, train a custom model, no license)
  or Picovoice Porcupine (instant custom keyword, needs a free access key). Either
  feeds the same `name` hub event, so only `sona/names/` changes. For a demo where
  the wearer's name is known in advance, KWS is both faster and more robust; leave
  it as the Tuesday/Wednesday call after seeing real far-field pickup.

## 8. Modes (focus / surround / alerts) — how to test with the array on the desk
- Mirror buttons switch modes. Focus gates captions by the utterance's bearing (mean of the
  chip's DOA_VALUE while speech was active). We tried fixing the array's beam to the front
  in focus mode (`XVF_FIXED_BEAM`) — it pins DOA_VALUE and the LED ring to the fixed
  direction, so everything looked "in front" and got printed. Leave it off.
- Preferences (name, mode, cone, sound list) persist in `out/settings.json` across restarts.
- Focus test: one person talks from the front (inside the cone arc) → captions appear; a
  second person talks from behind → their text shows in the mirror's HEARD log with a ⤫ and
  bearing but NOT on the glasses; they call the wearer's name → alert + wedge anyway.
- Cone presets 40/60/90/180° (default 60°). Tune `FOCUS_CONE_DEG`, and if partials flicker
  at the cone edge raise `FOCUS_PARTIAL_WINDOW_S`.
- Unknown bearing (no speech-active DoA during the utterance) fails OPEN: the caption is shown.

## 9. Own voice + sound bearings
- Enrol the wearer in the mirror (MY VOICE → ENROLL, ~20 s, alone). Then watch the `me 0.xx`
  tags in HEARD: the wearer should score above `OWN_VOICE_THRESHOLD` (0.60), everyone else
  below. Adjust the threshold in `sona/config.py` to sit between the two clusters, then tick
  "hide my own words". Profile lives in `out/voice_profile.json` (FORGET deletes it).
- A detected sound (siren…) takes the latest bearing the chip did NOT attribute to speech, and
  only follows the bearing while it moves without speech — a talker nearby no longer drags the
  siren's dot onto themselves. Name-calls use the bearing of the utterance that contained the name.

## 10. Demo wiring (Friday)
- Pi in a pocket/backpack; ReSpeaker on the hat (USB to Pi); G1 on the wearer.
- Projector laptop opens `http://<pi-ip>:8765` (phone-hotspot network).
- Sound cue: second phone playing a siren (YouTube "ambulance siren") moved around
  the wearer. Rehearse distances/volume — verify YAMNet catches the phone-speaker
  siren early (it usually does; if not, drop the threshold in SOUND_TARGETS).
- Name-call cue: a teammate off to the side calls the wearer's name — the arc swings
  to them. Strong, relatable demo beat straight from the interviews.
- Fallback brain: run the exact same app on the Mac with `--g1 --doa serial`.
