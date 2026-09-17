"""Central configuration. Everything tunable on hardware day lives here."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHISPER_DIR = ROOT / "sona_stt" / "whisper.cpp"
MODELS_DIR = ROOT / "models"

# --- audio capture ---
SAMPLE_RATE = 16000
FRAME_MS = 30
MIC_CHANNEL = (
    1  # 0-based input channel; reSpeaker USB: 0 = conference mix, 1 = ASR beam (best for STT)
)
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480

# --- VAD / utterance segmentation ---
VAD_AGGRESSIVENESS = 3  # 0..3, higher = stricter speech detection (3: fewer noise triggers)
VAD_TRIGGER_RATIO = 0.6  # voiced ratio in the window that opens an utterance
VAD_TRIGGER_WINDOW_MS = 240
VAD_END_SILENCE_MS = 250  # silence that closes an utterance
UTTERANCE_MAX_S = 8.0
UTTERANCE_MIN_S = 0.30

# --- speech to text (whisper.cpp server) ---
# small.en is markedly more robust to background noise; the M4 absorbs it easily.
# On the Pi start from base.en and revisit after the benchmark (pi/NOTES.md step 4).
STT_MODEL =  "base.en"
STT_LANGUAGE = "en"
STT_PORT = 8178
STT_PARTIALS = False  # transcribe in-progress speech for near-live captions
STT_PARTIAL_INTERVAL = 1.0  # s between partial passes
STT_PARTIAL_MIN_S = 1.0  # don't bother below this much audio
STT_NEAR_ONLY = True
STT_MIN_DBFS = -32.0

# Hallucination gate: YAMNet's live Speech score decides whether whisper's output
# on a segment is trustworthy (whisper invents "Thanks for watching." etc. on noise).
SPEECH_GATE_MIN = 0.12  # below this, drop the utterance without transcribing
SPEECH_GATE_SUSPECT = 0.50  # below this, drop known hallucination phrases

# --- name-call detection ---
# When someone calls the wearer's name (often from outside their field of view),
# alert them and point to the speaker using the ReSpeaker's speech-tuned DoA.
WEARER_NAMES: list[str] = ["Miquel"]  # editable live in the mirror or via --name
NAME_MATCH_RATIO = 0.82  # edit-distance ratio for a direct token match
NAME_SOUNDEX_RATIO = 0.55  # looser ratio accepted when phonetic codes agree
NAME_ALERT_TTL_S = 5.0  # how long a name alert stays on screen
NAME_COOLDOWN_S = 4.0  # suppress repeat alerts for the same name
NAME_DOA_WINDOW_S = 2.5  # look back this far to fix the caller's direction

# --- own-voice recognition (speaker verification) ---
# Enrol the wearer once (~20 s of speech) -> voice profile; utterances whose voice matches
# can then be hidden: the wearer doesn't want their own words on the display.
OWN_VOICE_MODEL = MODELS_DIR / "speaker" / "wespeaker_en_voxceleb_CAM++.onnx"
OWN_VOICE_THRESHOLD = 0.70  # cosine; measured same speaker 0.81, other 0.64 — tune per wearer
OWN_VOICE_ENROLL_S = 20.0  # seconds of the wearer's speech to collect at enrolment
OWN_VOICE_MIN_UTT_S = 0.8  # shorter utterances give unreliable embeddings; not judged
OWN_VOICE_IGNORE_DEFAULT = False  # off while debugging (Miquel wants to see his own captions)
SOUND_DOA_WINDOW_S = 4.0  # how far back a non-speech bearing may be used for a detected sound

# --- sound classification (YAMNet) ---
YAMNET_MODEL = MODELS_DIR / "yamnet" / "yamnet.tflite"
YAMNET_CLASS_MAP = MODELS_DIR / "yamnet" / "yamnet_class_map.csv"
SOUND_HOP_S = 0.25  # classify twice a second
SOUND_EMA_ALPHA = 0.75  # smoothing of scores between hops
SOUND_EVENT_TTL_S = 3.5  # how long a sound banner stays on screen
SOUND_LOG_COOLDOWN_S = 2.0

SOUND_ENABLED_DEFAULT = ("SIREN", "HORN", "DOORBELL", "ALARM", "DOG")  # shown on start
SOUND_DEFAULT_THRESHOLD = 0.35  # for classes added live from the mirror

# AudioSet display_name substring (lowercase) -> (LABEL, priority, threshold)
SOUND_TARGETS = {
    "siren": ("SIREN", 3, 0.18),
    "civil defense siren": ("SIREN", 3, 0.18),

    "vehicle horn": ("HORN", 2, 0.22),
    "air horn": ("HORN", 2, 0.22),
    "train horn": ("HORN", 3, 0.22),

    "car alarm": ("ALARM", 2, 0.22),
    "reversing beeps": ("BEEPS", 2, 0.25),

    "doorbell": ("DOORBELL", 2, 0.22),
    "ding-dong": ("DOORBELL", 2, 0.25),

    "knock": ("KNOCK", 1, 0.30),

    "smoke detector": ("ALARM", 3, 0.22),
    "fire alarm": ("ALARM", 3, 0.22),
    "alarm clock": ("ALARM", 1, 0.25),
    "buzzer": ("ALARM", 1, 0.25),

    "telephone bell ringing": ("PHONE", 1, 0.25),
    "ringtone": ("PHONE", 1, 0.25),

    "bark": ("DOG", 1, 0.25),
    "dog": ("DOG", 1, 0.30),

    "baby cry": ("BABY", 2, 0.25),

    "bicycle bell": ("BELL", 1, 0.25),
}
# --- modes ---
#   focus    : captions only from the cone in front (adjustable); alerts from everywhere
#   surround : captions from everywhere + alerts
#   alerts   : no captions; name-calls + important sounds only
MODES = ("focus", "surround", "alerts")
DEFAULT_MODE = "surround"
FOCUS_CONE_DEG = 60  # total width of the listening cone in focus mode (±30°)
FOCUS_CONE_PRESETS = (40, 60, 90, 180)
FOCUS_PARTIAL_WINDOW_S = 1.5  # bearing lookback used to gate live partial captions
# Fixing the array's focused beam to the front (AEC_FIXEDBEAMSONOFF) turned out to pin the
# chip's DOA_VALUE — and the LED ring — to that fixed direction, so every utterance looked
# like it came from the front and the cone gate let everything through. Keep it OFF: focus
# mode gates by the real bearing; the chip's own beam steering keeps working as shipped.
XVF_FIXED_BEAM = False
LIVE_DOA_DOT_MODES = ("surround",)  # modes that show the live speech bearing as a dot (never focus)

# --- display / UI ---
CANVAS_W, CANVAS_H = 576, 136  # G1 1-bit bitmap canvas
G1_TEXT_WIDTH = 40  # firmware text-mode line width
G1_TEXT_LINES = 5  # firmware text-mode lines per page

# Captions use a "page" model (pop-on captions): lines fill fixed row slots from the
# top down and never move once written. When a sentence doesn't fit in the rows left,
# the page clears and the sentence starts at the top; silence clears the page too.
CAPTION_LINES = 5  # rows per page (== G1 text-mode lines)
CAPTION_FONT_SIZE = 18  # px on the 576x136 canvas
CAPTION_LINE_PITCH = 24  # px between rows (5 rows -> 8 + 4*24 + 21 = 125 px)
CAPTION_TOP = 8  # px, first row
CAPTION_COL = (136, 570)  # x-range of the caption column (ring lives left of it)
CAPTION_ALIGN = "left"  # "left": eye returns to the same x each row (page-fill reading)
CAPTION_IDLE_CLEAR_S = 6.0  # no new speech for this long -> clear the page
WRAP_WIDTH = 39  # chars per row: 39 x Menlo-18 = 423 px in the 434 px column
RENDER_FPS = 10  # mirror refresh
MIRROR_PORT = 8765
G1_TEXT_MIN_INTERVAL = 0.35  # s between BLE text pushes
G1_BMP_MIN_INTERVAL = 1.2  # s between BLE bitmap pushes (measure real rate on hardware)

# screen_status byte for 0x4E text packets.
# even_glasses uses 0x31 (NEW_CONTENT|DISPLAYING); other clients use 0x71. Verify on hardware.
G1_SCREEN_STATUS = 0x31

# --- direction of arrival ---
# XVF3800 reports 0..359 with 0 at the connector (cable) edge — firmware/xvf3800/doa_convention.jpg.
# Mounting: board component-side up, cable at the BACK of the head, so the cable edge is 180°
# in Sona's frame (0 = wearer's front, clockwise):
#   sona = (XVF_DOA_SIGN * raw + AZIMUTH_OFFSET_DEG) % 360
XVF_DOA_SIGN = 1  # set to -1 if the board is mounted component-side down (left/right mirror)
AZIMUTH_OFFSET_DEG = 180.0  # cable at the back; fine-tune until a clap in front reads 0°
XVF_DOA_HOLD_S = (
    1.5  # bearing counts as live this long after it last moved (sirens don't raise speech)
)
XVF_RAW_MIC_CHANNELS = slice(2, 6)  # 6ch USB firmware: ch1-2 processed, ch3-6 raw mics 0-3
SERIAL_BAUD = 115200

FONT_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",  # macOS
    "/System/Library/Fonts/Monaco.ttf",  # macOS fallback
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",  # Raspberry Pi OS
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]
