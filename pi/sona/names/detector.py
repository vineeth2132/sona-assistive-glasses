"""Watches captions (final + partial) for the wearer's name and fires 'name' events.

Runs on the transcript we already produce, so it needs no extra model and works with
any name typed at runtime. Direction is attached later by the state worker, from the
buffered speech DoA at the moment the name was heard.
"""

import asyncio
import logging
import time

from .. import config
from .matcher import NameMatcher

log = logging.getLogger(__name__)


class NameDetector:
    def __init__(self, hub, names=None):
        self.hub = hub
        self.matcher = NameMatcher(
            names if names is not None else config.WEARER_NAMES,
            config.NAME_MATCH_RATIO,
            config.NAME_SOUNDEX_RATIO,
        )
        self._last_fire: dict[str, float] = {}
        log.info("name detector watching: %s", ", ".join(self.matcher.names) or "(none)")

    def _fire(self, text: str, angle: float | None = None):
        name = self.matcher.match(text)
        if not name:
            return
        now = time.time()
        if now - self._last_fire.get(name, 0) < config.NAME_COOLDOWN_S:
            return
        self._last_fire[name] = now
        log.info("name called: %s", name)
        # the utterance's own bearing when we have it (finals); partials fall back to the
        # most recent speech bearing in the state worker
        self.hub.publish("name", {"name": name, "t": now, "angle": angle})

    async def run(self):
        caption_q = self.hub.subscribe("caption")
        transcript_q = self.hub.subscribe("transcript")  # every STT result, shown or not
        partial_q = self.hub.subscribe("partial")
        setname_q = self.hub.subscribe("name_set")

        async def watch(q):
            while True:
                item = await q.get()
                if isinstance(item, dict):
                    if not item.get("own"):  # the wearer saying their own name is not a call
                        self._fire(item["text"], item.get("angle"))
                else:
                    self._fire(item)

        async def reconfigure():
            while True:
                names = await setname_q.get()
                if isinstance(names, str):
                    names = [n.strip() for n in names.split(",")]
                self.matcher.set_names(names)
                self._last_fire.clear()
                log.info("name detector updated: %s", ", ".join(self.matcher.names) or "(none)")

        await asyncio.gather(watch(caption_q), watch(transcript_q), watch(partial_q), reconfigure())
