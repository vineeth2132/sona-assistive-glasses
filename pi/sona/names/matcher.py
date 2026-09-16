"""Spot the wearer's name in transcribed text.

Whisper rarely spells an unusual name the way it sounds — "Miquel" comes back as
"Michael", "Miguel", "Mikel", "Mikkel". So we match on two axes at once:
  * edit-distance ratio (catches typos / small slips), and
  * a Soundex phonetic code (catches homophones that are spelled differently).

Zero dependencies on purpose: this has to run offline on the Pi, and a dedicated
keyword-spotting model (openWakeWord / Porcupine) is the planned hardware-day upgrade
for lower latency and better far-field pickup — see pi/NOTES.md.
"""

import re

_WORD = re.compile(r"[a-z]+")  # split on apostrophes too: "Miquel's" -> miquel, s


def _soundex(word: str) -> str:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return ""
    codes = {
        **dict.fromkeys("bfpv", "1"),
        **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"),
        "l": "4",
        **dict.fromkeys("mn", "5"),
        "r": "6",
    }
    first = word[0]
    out = ""
    prev = codes.get(first, "")
    for ch in word[1:]:
        c = codes.get(ch, "")
        if c and c != prev:
            out += c
        if ch not in "hw":
            prev = c
    return (first + out + "000")[:4].upper()


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _ratio(a: str, b: str) -> float:
    m = max(len(a), len(b))
    return 1.0 - _levenshtein(a, b) / m if m else 1.0


class NameMatcher:
    def __init__(self, names, match_ratio: float, soundex_ratio: float):
        self.match_ratio = match_ratio
        self.soundex_ratio = soundex_ratio
        self.set_names(names)

    def set_names(self, names) -> None:
        self._targets = []  # (display, lowercase, soundex)
        for n in names:
            n = (n or "").strip()
            if n:
                self._targets.append((n, n.lower(), _soundex(n)))

    @property
    def names(self) -> list[str]:
        return [t[0] for t in self._targets]

    def match(self, text: str) -> str | None:
        """Return the display-form name if any target is spoken in `text`."""
        if not text or not self._targets:
            return None
        tokens = _WORD.findall(text.lower())
        for tok in tokens:
            if len(tok) < 3:  # avoid matching on "an", "in", etc.
                continue
            tok_sx = _soundex(tok)
            for disp, low, sx in self._targets:
                if tok == low:
                    return disp
                r = _ratio(tok, low)
                if r >= self.match_ratio:
                    return disp
                if sx and tok_sx == sx and r >= self.soundex_ratio:
                    return disp
        return None
