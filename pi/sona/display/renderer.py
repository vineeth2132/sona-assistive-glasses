"""Renders UiState into the exact 576x136 1-bit frame the G1 can display.

The same frame feeds the web mirror (styled green, scaled up) and, in bitmap mode,
the glasses themselves. Text mode sends UiState.glass_text() instead.

Layout: compass ring on the left — a dot/wedge on the ring marks where a detected sound
or name-call came from, with its label inside; in focus mode the listening cone is a thick
arc (and stands in for the front marker). Captions on the right in fixed row slots (page
model — rows never move). The ring is always present because alerts exist in every mode.
"""

import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .. import config

GREEN = (94, 255, 158)
LABEL_SIZES = (20, 18, 16, 14, 12)


def _load_font(size: int):
    for path in config.FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


class Renderer:
    def __init__(self):
        self.font = _load_font(config.CAPTION_FONT_SIZE)
        self.label_fonts = {s: _load_font(s) for s in LABEL_SIZES}

    def _fit_label(self, d, text, cx, cy, max_w):
        for size in LABEL_SIZES:
            f = self.label_fonts[size]
            w = d.textlength(text, font=f)
            if w <= max_w or size == LABEL_SIZES[-1]:
                d.text((cx - w / 2, cy - size / 2 - 1), text, font=f, fill=255)
                return

    def _compass(self, d, ev, doa_angle, doa_active, cone_deg=None, live_dot=False):
        """Ring + (focus) cone arc + a marker where a detected sound or name-call came from.
        Focus mode: the cone itself says where the front is, so no front triangle and no
        live-bearing dot — the ring stays clean until something important happens.
        Surround mode shows the live speech bearing as a dot (LIVE_DOA_DOT_MODES)."""
        cx, cy, r = 64, config.CANVAS_H // 2, 50
        is_name = ev is not None and ev.kind == "name"
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=255, width=2)
        if is_name:  # emphasis: double ring
            d.ellipse([cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4], outline=255, width=1)
        if cone_deg:  # focus mode: the listening cone, centred on the front
            half = cone_deg / 2
            pad = 3
            # PIL arcs run clockwise from 3 o'clock; our 0° is 12 o'clock
            d.arc(
                [cx - r + pad, cy - r + pad, cx + r - pad, cy + r - pad],
                start=-90 - half,
                end=-90 + half,
                fill=255,
                width=6,
            )
        else:  # front marker (the cone plays that role in focus mode)
            d.polygon([(cx - 5, cy - r + 2), (cx + 5, cy - r + 2), (cx, cy - r + 10)], fill=255)

        angle = ev.angle if (ev and ev.angle is not None) else None
        if angle is None and live_dot and doa_active:
            angle = doa_angle
        if angle is not None:
            a = math.radians(angle % 360)
            px = cx + math.sin(a) * (r - 12)
            py = cy - math.cos(a) * (r - 12)
            if is_name:  # bold wedge pointing outward
                perp = a + math.pi / 2
                tipx, tipy = cx + math.sin(a) * (r - 1), cy - math.cos(a) * (r - 1)
                b1 = (px + math.sin(perp) * 7, py - math.cos(perp) * 7)
                b2 = (px - math.sin(perp) * 7, py + math.cos(perp) * 7)
                d.polygon([b1, b2, (tipx, tipy)], fill=255)
            else:
                d.ellipse([px - 8, py - 8, px + 8, py + 8], fill=255)
        if ev is not None:
            self._fit_label(d, ev.label, cx, cy, 2 * (r - 14))

    def render(self, state) -> Image.Image:
        img = Image.new("L", (config.CANVAS_W, config.CANVAS_H), 0)
        d = ImageDraw.Draw(img)

        name = state.active_name()
        sound = state.active_sound()
        cone = state.cone_deg if state.mode == "focus" else None
        live = state.mode in config.LIVE_DOA_DOT_MODES
        self._compass(
            d, name or sound, state.doa_angle, state.doa_active, cone_deg=cone, live_dot=live
        )

        if state.show_captions:
            x_left, x_right = config.CAPTION_COL
            y = config.CAPTION_TOP
            for line in state.caption_rows():
                if config.CAPTION_ALIGN == "right":
                    x = x_right - d.textlength(line, font=self.font)
                else:
                    x = x_left
                d.text((x, y), line, font=self.font, fill=255)
                y += config.CAPTION_LINE_PITCH

        return img

    @staticmethod
    def to_png_bytes(img: Image.Image, scale: int = 2) -> bytes:
        arr = np.asarray(img, dtype=np.float32) / 255.0
        rgb = (arr[..., None] * np.array(GREEN, dtype=np.float32)).astype(np.uint8)
        out = Image.fromarray(rgb, "RGB").resize(
            (img.width * scale, img.height * scale), Image.NEAREST
        )
        buf = io.BytesIO()
        out.save(buf, "PNG")
        return buf.getvalue()

    @staticmethod
    def to_bmp_bytes(img: Image.Image) -> bytes:
        bw = img.point(lambda p: 255 if p > 127 else 0).convert("1")
        buf = io.BytesIO()
        bw.save(buf, "BMP")
        return buf.getvalue()
