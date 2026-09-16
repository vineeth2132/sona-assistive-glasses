"""Tiny asyncio pub/sub bus. Slow subscribers drop their oldest message.

Topics used across the app:
  frames    -> np.int16 mono 30 ms audio frames @16 kHz
  caption   -> str, one finished (gated) utterance
  partial   -> str, in-progress utterance text ("" clears it)
  speech    -> float, YAMNet's live Speech score (hallucination gate for captions)
  sound     -> {"label": str, "score": float}
  name      -> {"name": str, "angle": float | None}  the wearer's name was spoken
  name_set  -> str, comma-separated names to watch for (runtime reconfigure)
  transcript-> {"text", "angle", "me": similarity to the wearer's voice | None, "own": bool}
  sound_targets -> list of watch-list entries (which YAMNet classes are displayed)
  xvf_config-> {"focus": bool}  array configuration for the current mode
  cone      -> float, focus cone width in degrees
  doa       -> {"angle": float | None (0=front, clockwise), "active": bool,
                "speech": bool | None (is this bearing a talker?), "moved": bool}
  mode      -> "focus" | "surround" | "alerts"
"""

import asyncio
from collections import defaultdict


class Hub:
    def __init__(self):
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, topic: str, maxsize: int = 128) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs[topic].append(q)
        return q

    def publish(self, topic: str, msg) -> None:
        for q in self._subs[topic]:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(msg)
