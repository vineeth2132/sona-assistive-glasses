"""Web mirror: shows exactly what the glasses render, live, in a browser.

Doubles as:
(a) the dev simulator before hardware arrives
(b) the projector view for the demo

It also provides the WebSocket used by the G2 application.
"""

import asyncio
import base64
import json
import logging
from pathlib import Path

from aiohttp import WSMsgType, web

from .. import config


log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"

# Payload includes:
# - live DoA
# - live partial transcript
# - sound label
# - sound-specific direction
# - sound confidence
# - name direction
PROTOCOL_VERSION = 6


class MirrorServer:
    def __init__(
        self,
        hub,
        state,
        renderer,
        port: int = config.MIRROR_PORT,
    ):
        self.hub = hub
        self.state = state
        self.renderer = renderer
        self.port = port

        self.clients: set[
            web.WebSocketResponse
        ] = set()

    # ==================================================
    # SERVER
    # ==================================================

    async def start(self):
        app = web.Application()

        app.router.add_get(
            "/",
            self._index,
        )

        app.router.add_get(
            "/ws",
            self._ws,
        )

        runner = web.AppRunner(
            app,
            access_log=None,
        )

        await runner.setup()

        site = web.TCPSite(
            runner,
            "0.0.0.0",
            self.port,
        )

        try:
            await site.start()

        except OSError as e:
            raise SystemExit(
                f"port {self.port} is already in use — "
                f"is another sona instance running? "
                f"(check: lsof -nP -iTCP:{self.port} "
                f"-sTCP:LISTEN) [{e.strerror}]"
            ) from None

        log.info(
            "mirror running at http://localhost:%d",
            self.port,
        )

    # ==================================================
    # WEB PAGE
    # ==================================================

    async def _index(self, _req):
        return web.FileResponse(
            WEB_DIR / "index.html",
            headers={
                "Cache-Control":
                    "no-store, must-revalidate"
            },
        )

    # ==================================================
    # WEBSOCKET
    # ==================================================

    async def _ws(self, req):
        ws = web.WebSocketResponse(
            heartbeat=20
        )

        await ws.prepare(req)

        self.clients.add(ws)

        log.info(
            "mirror client connected (%d total)",
            len(self.clients),
        )

        await ws.send_str(
            json.dumps(
                {
                    "type": "init",
                    "version":
                        PROTOCOL_VERSION,

                    "classes":
                        self.state.sounds.class_names,
                }
            )
        )

        # Force an immediate frame.
        self.state.dirty = True

        try:
            async for msg in ws:

                if (
                    msg.type !=
                    WSMsgType.TEXT
                ):
                    continue

                try:
                    data = json.loads(
                        msg.data
                    )

                except json.JSONDecodeError:
                    continue

                self._handle(
                    data
                )

        finally:
            self.clients.discard(
                ws
            )

            log.info(
                "mirror client disconnected (%d total)",
                len(self.clients),
            )

        return ws

    # ==================================================
    # COMMANDS FROM CLIENT
    # ==================================================

    def _handle(
        self,
        data: dict,
    ):
        t = data.get(
            "type"
        )

        # ------------------------------------------
        # Simulated caption
        # ------------------------------------------

        if (
            t == "say"
            and data.get("text")
        ):
            self.hub.publish(
                "caption",
                str(
                    data["text"]
                )[:300],
            )

        # ------------------------------------------
        # Mode
        # ------------------------------------------

        elif (
            t == "mode"
            and data.get("value")
            in config.MODES
        ):
            self.hub.publish(
                "mode",
                data["value"],
            )

        # ------------------------------------------
        # Focus cone
        # ------------------------------------------

        elif (
            t == "cone"
            and isinstance(
                data.get("value"),
                (int, float),
            )
        ):
            self.hub.publish(
                "cone",
                max(
                    20,
                    min(
                        360,
                        int(
                            data["value"]
                        ),
                    ),
                ),
            )

        # ------------------------------------------
        # Sound toggles
        # ------------------------------------------

        elif (
            t == "sound_toggle"
            and data.get("label")
        ):
            if self.state.sounds.toggle(
                str(
                    data["label"]
                ),
                bool(
                    data.get(
                        "enabled"
                    )
                ),
            ):
                self._sounds_changed()

        elif (
            t == "sound_add"
            and data.get("cls")
        ):
            if self.state.sounds.add(
                str(
                    data["cls"]
                ),
                data.get("label")
                or None,
            ):
                self._sounds_changed()

        elif (
            t == "sound_remove"
            and data.get("label")
        ):
            if self.state.sounds.remove(
                str(
                    data["label"]
                )
            ):
                self._sounds_changed()

        # ------------------------------------------
        # Own voice
        # ------------------------------------------

        elif (
            t == "voice_enroll"
            and self.state.voice
        ):
            self.state.voice.start_enrollment()
            self.state.dirty = True

        elif (
            t == "voice_cancel"
            and self.state.voice
        ):
            self.state.voice.cancel_enrollment()
            self.state.dirty = True

        elif (
            t == "voice_forget"
            and self.state.voice
        ):
            self.state.voice.forget()
            self.state.dirty = True

        elif (
            t == "voice_ignore"
        ):
            self.state.ignore_own_voice = bool(
                data.get(
                    "enabled"
                )
            )

            self.state.persist()

            self.state.dirty = True

        # ------------------------------------------
        # Wearer name
        # ------------------------------------------

        elif (
            t == "name_set"
        ):
            self.hub.publish(
                "name_set",
                str(
                    data.get(
                        "value",
                        "",
                    )
                )[:80],
            )

        # ------------------------------------------
        # Debug line from the phone app (g2/src/main.ts debug())
        # ------------------------------------------

        elif t == "log":
            log.info(
                "phone: %s",
                str(data.get("text", ""))[:200],
            )

        elif (
            t == "name_call"
            and data.get("name")
        ):
            angle = data.get(
                "angle"
            )

            self.hub.publish(
                "name",
                {
                    "name":
                        str(
                            data["name"]
                        )[:20],

                    "angle":
                        (
                            float(angle) %
                            360

                            if isinstance(
                                angle,
                                (int, float),
                            )

                            else None
                        ),
                },
            )

    # ==================================================
    # SOUND WATCHLIST CHANGE
    # ==================================================

    def _sounds_changed(
        self,
    ):
        self.hub.publish(
            "sound_targets",
            self.state.sounds.entries(),
        )

        self.state.persist()

        self.state.dirty = True

    # ==================================================
    # BROADCAST LOOP
    # ==================================================

    async def broadcast_loop(
        self,
    ):
        interval = (
            1.0 /
            config.RENDER_FPS
        )

        keepalive = 0.0

        while True:
            await asyncio.sleep(
                interval
            )

            sound = (
                self.state.active_sound()
            )

            name = (
                self.state.active_name()
            )

            keepalive += (
                interval
            )

            # Send whenever state changed,
            # alert active, or every 0.5 s.
            if not (
                self.state.dirty
                or sound
                or name
                or keepalive > 0.5
            ):
                continue

            keepalive = 0.0

            self.state.dirty = False

            if not self.clients:
                continue

            # ------------------------------------------
            # Browser mirror image
            # ------------------------------------------

            img = (
                self.renderer.render(
                    self.state
                )
            )

            png = (
                self.renderer.to_png_bytes(
                    img
                )
            )

            # ------------------------------------------
            # WebSocket payload
            # ------------------------------------------

            payload = json.dumps(
                {
                    "type":
                        "frame",

                    "version":
                        PROTOCOL_VERSION,

                    "frame":
                        base64.b64encode(
                            png
                        ).decode(),

                    "sounds":
                        self.state.sounds.entries(),

                    "voice": {
                        **(
                            self.state.voice.status()

                            if self.state.voice

                            else {
                                "available":
                                    False,

                                "reason":
                                    "not started",
                            }
                        ),

                        "ignore":
                            self.state.ignore_own_voice,
                    },

                    # ==================================================
                    # DATA USED BY G2
                    # ==================================================

                    "state": {
                        # --------------------------
                        # UI mode
                        # --------------------------

                        "mode":
                            self.state.mode,

                        "cone":
                            self.state.cone_deg,

                        "names":
                            self.state.names,

                        # --------------------------
                        # Live XVF direction
                        # --------------------------

                        "angle":
                            self.state.doa_angle,

                        "doa_active":
                            self.state.doa_active,

                        "doa_speech":
                            self.state.doa_speech,

                        # --------------------------
                        # Live STT partial
                        # --------------------------

                        "partial":
                            self.state.partial,

                        # --------------------------
                        # Environmental sound
                        # --------------------------

                        "sound":
                            (
                                sound.label
                                if sound
                                else None
                            ),

                        "sound_angle":
                            (
                                sound.angle
                                if sound
                                else None
                            ),

                        "sound_score":
                            (
                                sound.score
                                if sound
                                else None
                            ),

                        # --------------------------
                        # Name alert
                        # --------------------------

                        "name_alert":
                            (
                                name.label
                                if name
                                else None
                            ),

                        "name_angle":
                            (
                                name.angle
                                if name
                                else None
                            ),

                        # --------------------------
                        # Captions
                        # --------------------------

                        "history": [
                            {
                                "text":
                                    h["text"],

                                "angle":
                                    h["angle"],

                                "shown":
                                    h["shown"],

                                "me":
                                    h.get(
                                        "me"
                                    ),

                                "own":
                                    h.get(
                                        "own",
                                        False,
                                    ),
                            }

                            for h in list(
                                self.state.transcripts
                            )[-10:]
                        ],
                    },
                }
            )

            # ------------------------------------------
            # Send
            # ------------------------------------------

            dead = []

            # Snapshot: a client may disconnect (and remove itself from the
            # set) while we await a send, which would crash the iteration.
            for ws in list(
                self.clients
            ):
                try:
                    await ws.send_str(
                        payload
                    )

                except ConnectionError:
                    dead.append(
                        ws
                    )

            for ws in dead:
                self.clients.discard(
                    ws
                )