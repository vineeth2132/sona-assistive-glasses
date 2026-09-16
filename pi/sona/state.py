"""Shared UI state: what the wearer should be seeing right now.

Captions follow a page model ("pop-on" captions): rows fill from the top down and
never move once written. A sentence that doesn't fit in the remaining rows clears the
page and starts at the top; a stretch of silence clears the page as well.

Modes:  focus    — captions only from the cone in front; alerts from everywhere
        surround — captions from everywhere + alerts
        alerts   — no captions; name-calls and important sounds only
"""

import json
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field

from . import config
from .sounds.watchlist import SoundWatchlist

log = logging.getLogger(__name__)
SETTINGS_PATH = config.ROOT / "out" / "settings.json"  # user preferences, survive restarts


@dataclass
class SoundEvent:
    label: str
    score: float = 0.0
    angle: float | None = None  # degrees, 0 = front, clockwise; None = unknown
    kind: str = "sound"  # "sound" (YAMNet) or "name" (your name was called)
    t: float = field(default_factory=time.time)

    @property
    def ttl(self) -> float:
        return config.NAME_ALERT_TTL_S if self.kind == "name" else config.SOUND_EVENT_TTL_S

    @property
    def alive(self) -> bool:
        return time.time() - self.t <= self.ttl


def wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= width:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def bearing_banner(ev: SoundEvent) -> str:
    """Direction as text — used on the glasses in text mode (no graphics there)."""
    tag = f"* {ev.label}" if ev.kind == "name" else ev.label  # '*' marks your name
    if ev.angle is None:
        return f"!! {tag} !!"
    a = ev.angle % 360
    if a < 30 or a > 330:
        return f"^ {tag} AHEAD ^"
    if a < 150:
        return f"{tag} >>>"
    if a < 210:
        return f"v {tag} BEHIND v"
    return f"<<< {tag}"


def angular_distance(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, in degrees."""
    return abs((a - b + 180) % 360 - 180)


def circular_mean(angles) -> float:
    s = sum(math.sin(math.radians(a)) for a in angles)
    c = sum(math.cos(math.radians(a)) for a in angles)
    return math.degrees(math.atan2(s, c)) % 360


class UiState:
    def __init__(self):
        self.history: deque[str] = deque(maxlen=200)  # captions that were shown
        self.transcripts: deque[dict] = deque(maxlen=200)  # everything heard (mirror log)
        self.page: list[str] = []  # committed rows on the current page
        self.partial: str | None = None  # in-progress utterance text
        self.last_activity = 0.0  # last caption/partial update
        self.sound: SoundEvent | None = None
        self.name_event: SoundEvent | None = None
        self.doa_angle: float | None = None
        self.doa_active = False
        self.doa_hist: deque[tuple[float, float]] = deque(maxlen=256)  # (t, angle) of SPEECH
        self.sound_hist: deque[tuple[float, float]] = deque(maxlen=64)  # (t, angle) of non-speech
        self.doa_speech = False  # is the current bearing a talker (chip's speech flag)?
        self.voice = None  # OwnVoice, attached by the app
        self.ignore_own_voice = config.OWN_VOICE_IGNORE_DEFAULT
        self.speech_scores: deque[float] = deque(maxlen=8)  # recent YAMNet Speech scores
        self.mode = config.DEFAULT_MODE
        self.sounds = SoundWatchlist()  # which YAMNet sounds get displayed
        self.names: list[str] = list(config.WEARER_NAMES)  # what the name detector listens for
        self.cone_deg = float(config.FOCUS_CONE_DEG)
        self.dirty = True

    # --- persistence of user preferences ---
    def persist(self) -> None:
        try:
            SETTINGS_PATH.parent.mkdir(exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(
                    {
                        "names": self.names,
                        "mode": self.mode,
                        "cone_deg": self.cone_deg,
                        "sounds": self.sounds.entries(),
                        "ignore_own_voice": self.ignore_own_voice,
                    },
                    indent=1,
                )
            )
        except OSError as e:
            log.warning("could not save settings: %s", e)

    def restore(self) -> bool:
        try:
            data = json.loads(SETTINGS_PATH.read_text())
        except (OSError, ValueError):
            return False
        names = data.get("names")
        if isinstance(names, list) and names:
            self.names = [str(n)[:40] for n in names if str(n).strip()]
        if data.get("mode") in config.MODES:
            self.mode = data["mode"]
        cone = data.get("cone_deg")
        if isinstance(cone, (int, float)) and 20 <= cone <= 360:
            self.cone_deg = float(cone)
        if isinstance(data.get("sounds"), list):
            self.sounds.restore(data["sounds"])
        if isinstance(data.get("ignore_own_voice"), bool):
            self.ignore_own_voice = data["ignore_own_voice"]
        return True

    # --- modes ---
    @property
    def show_captions(self) -> bool:
        return self.mode in ("focus", "surround")

    def caption_allowed(self, angle: float | None) -> bool:
        """Does speech from `angle` (Sona frame; None = unknown) get captioned in this mode?"""
        if self.mode == "alerts":
            return False
        if self.mode == "surround" or angle is None:  # unknown bearing: fail open
            return True
        return angular_distance(angle, 0.0) <= self.cone_deg / 2

    # --- captions (page model) ---
    def _make_room(self, lines: list[str]) -> list[str]:
        """Clear the page if `lines` won't fit below the current rows; cap huge inputs."""
        n = config.CAPTION_LINES
        if len(lines) > n:
            lines = lines[-n:]
        if len(self.page) + len(lines) > n:
            self.page.clear()  # in place: callers may hold a reference to the list
        return lines

    def add_caption(self, text: str) -> None:
        self.history.append(text)
        lines = self._make_room(wrap(text, config.WRAP_WIDTH))
        self.page.extend(lines)
        self.partial = None
        self.last_activity = time.time()
        self.dirty = True

    def add_transcript(
        self,
        text: str,
        angle: float | None,
        shown: bool,
        me: float | None = None,
        own: bool = False,
    ) -> None:
        self.transcripts.append(
            {"text": text, "angle": angle, "shown": shown, "me": me, "own": own, "t": time.time()}
        )
        self.dirty = True

    def set_partial(self, text: str) -> None:
        text = text or None
        if text:
            self._make_room(wrap(text + "…", config.WRAP_WIDTH))
            self.last_activity = time.time()
        self.partial = text
        self.dirty = True

    def caption_rows(self) -> list[str]:
        """Rows top-to-bottom: committed page, then the live partial in the free slots."""
        rows = list(self.page)
        if self.partial:
            rows += wrap(self.partial + "…", config.WRAP_WIDTH)
        return rows[-config.CAPTION_LINES :] if len(rows) > config.CAPTION_LINES else rows

    def clear_captions(self) -> None:
        self.page.clear()
        self.partial = None
        self.dirty = True

    def expire_idle(self, now: float | None = None) -> bool:
        """Clear the page after a stretch of silence. Returns True if it did."""
        now = now or time.time()
        if (self.page or self.partial) and now - self.last_activity > config.CAPTION_IDLE_CLEAR_S:
            self.clear_captions()
            return True
        return False

    # --- speech confidence (from YAMNet) ---
    def note_speech(self, score: float) -> None:
        self.speech_scores.append(float(score))

    def recent_speech(self) -> float | None:
        return max(self.speech_scores) if self.speech_scores else None

    # --- direction of arrival ---
    def record_doa(
        self, angle: float | None, active: bool, speech: bool | None = None, moved: bool = False
    ) -> None:
        """speech=True: the bearing is a talker; False: a non-speech source moved the estimate;
        None: the source can't tell (treated as speech for gating, as sound when it moves)."""
        self.doa_angle = angle
        self.doa_active = active and angle is not None
        self.doa_speech = bool(speech)
        if angle is None:
            return
        now = time.time()
        if speech or (speech is None and self.doa_active):
            self.doa_hist.append((now, angle))
        if not speech and moved:
            self.sound_hist.append((now, angle))

    def sound_direction(self, window: float = config.SOUND_DOA_WINDOW_S) -> float | None:
        """Bearing for a detected sound: the latest bearing NOT attributed to speech."""
        now = time.time()
        if self.sound_hist and now - self.sound_hist[-1][0] <= window:
            return self.sound_hist[-1][1]
        last_speech_t = self.doa_hist[-1][0] if self.doa_hist else 0.0
        if (
            self.doa_active
            and not self.doa_speech
            and self.doa_angle is not None
            and now - last_speech_t > config.XVF_DOA_HOLD_S
        ):
            return self.doa_angle  # the estimate is currently parked on a non-speech source
        return None

    def recent_direction(self, window: float) -> float | None:
        """Circular mean of speech-active bearings in the last `window` s; None if none."""
        now = time.time()
        angs = [a for t, a in self.doa_hist if now - t <= window]
        return circular_mean(angs) if angs else None

    def speaker_direction(self, window: float = config.NAME_DOA_WINDOW_S) -> float | None:
        """Where the current/last talker is; falls back to the last known bearing."""
        recent = self.recent_direction(window)
        return recent if recent is not None else self.doa_angle

    def direction_between(self, t0: float, t1: float) -> float | None:
        """Mean bearing of speech-active readings during [t0, t1] (with a little slack)."""
        angs = [a for t, a in self.doa_hist if t0 - 0.5 <= t <= t1 + 0.3]
        return circular_mean(angs) if angs else None

    # --- events ---
    def set_sound(self, ev: SoundEvent) -> None:
        self.sound = ev
        self.dirty = True

    def set_name(self, ev: SoundEvent) -> None:
        self.name_event = ev
        self.dirty = True

    def active_sound(self) -> SoundEvent | None:
        return self.sound if self.sound and self.sound.alive else None

    def active_name(self) -> SoundEvent | None:
        return self.name_event if self.name_event and self.name_event.alive else None

    def glass_text(self) -> str:
        """Payload for the G1 text protocol: the caption page, with an alert banner
        overlaid on the top (oldest) row so the other rows never shift."""
        rows = self.caption_rows() if self.show_captions else []
        alert = self.active_name() or self.active_sound()  # your name always wins
        if alert:
            banner = bearing_banner(alert)
            if rows:
                rows[0] = banner
            else:
                rows = [banner]
        return "\n".join(rows)
