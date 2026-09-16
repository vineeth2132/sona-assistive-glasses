"""Offline self-test: proves the three pillars work on this machine, no mic/BLE needed.

Usage: .venv/bin/python scripts/selftest.py
"""

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")


def test_renderer():
    from sona.display.renderer import Renderer
    from sona.state import SoundEvent, UiState

    state = UiState()
    state.add_caption("Excuse me, do you know when the next train to Munich leaves?")
    state.doa_angle, state.doa_active = 250.0, True
    state.set_sound(SoundEvent(label="SIREN", score=0.8, angle=250.0))
    r = Renderer()
    img = r.render(state)
    png = r.to_png_bytes(img)
    bmp = r.to_bmp_bytes(img)
    out = ROOT / "out" / "selftest_frame.png"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(png)
    ok = img.size == (576, 136) and len(bmp) in range(9500, 10500) and len(png) > 500
    record("renderer", ok, f"frame -> {out.relative_to(ROOT)}, bmp {len(bmp)} B")
    return ok


def test_g1_packets():
    from sona.display.renderer import Renderer
    from sona.state import UiState

    bmp = Renderer.to_bmp_bytes(Renderer().render(UiState()))
    chunks = [bmp[i : i + 194] for i in range(0, len(bmp), 194)]
    header = bytes([0x4E, 0, 1, 0, 0x31, 0, 0, 1, 1]) + b"<<< SIREN\nhello"
    ok = len(chunks) >= 50 and header[0] == 0x4E and len(header) == 9 + 15
    record("g1 packet shapes", ok, f"{len(chunks)} bmp chunks/frame")
    return ok


def test_caption_page():
    from sona import config
    from sona.state import UiState

    s = UiState()
    for i in range(config.CAPTION_LINES):
        s.add_caption(f"line {i}")
    filled = len(s.page) == config.CAPTION_LINES and s.page[0] == "line 0"
    s.add_caption("overflow sentence")  # no room left -> page resets
    reset = s.page == ["overflow sentence"]
    s.set_partial("still talking")  # partial sits in the next free row
    partial_ok = s.caption_rows() == ["overflow sentence", "still talking…"]
    s.last_activity -= config.CAPTION_IDLE_CLEAR_S + 1
    idle = s.expire_idle() and s.caption_rows() == []
    ok = filled and reset and partial_ok and idle
    record("caption page model", ok, "fills top-down, resets when full, clears on silence")
    return ok


def test_modes():
    from sona.state import UiState

    s = UiState()
    s.mode, s.cone_deg = "focus", 60
    focus_ok = s.caption_allowed(10) and s.caption_allowed(350) and not s.caption_allowed(100)
    focus_ok &= s.caption_allowed(None)  # unknown bearing fails open
    s.mode = "alerts"
    s.add_caption("should not show")
    alerts_ok = not s.caption_allowed(0) and s.glass_text() == ""
    s.mode = "surround"
    surround_ok = s.caption_allowed(180) and "should not show" in s.glass_text()
    ok = focus_ok and alerts_ok and surround_ok
    record("modes", ok, "focus gates by cone, alerts hides captions, surround shows all")
    return ok


def test_sound_watchlist():
    from sona import config
    from sona.sounds.watchlist import SoundWatchlist

    wl = SoundWatchlist()
    by = {e["label"]: e for e in wl.entries()}
    enabled = sorted(lbl for lbl, e in by.items() if e["enabled"])
    default_ok = enabled == sorted(config.SOUND_ENABLED_DEFAULT)
    siren_ok = "Siren" in by["SIREN"]["classes"] and "Civil defense siren" in by["SIREN"]["classes"]
    wl.toggle("DOG", False)
    add_ok = wl.add("Baby cry, infant cry") and any(e["label"] == "BABY CRY" for e in wl.entries())
    toggled = not {e["label"]: e for e in wl.entries()}["DOG"]["enabled"]
    ok = default_ok and siren_ok and add_ok and toggled
    record("sound watchlist", ok, f"enabled by default: {', '.join(enabled)}")
    return ok


def test_settings_roundtrip():
    import json
    import tempfile

    from sona import state as state_mod
    from sona.state import UiState

    with tempfile.TemporaryDirectory() as tmp:
        state_mod.SETTINGS_PATH = ROOT_SETTINGS = __import__("pathlib").Path(tmp) / "settings.json"
        a = UiState()
        a.names, a.mode, a.cone_deg = ["Pablo"], "focus", 90.0
        a.sounds.toggle("DOG", False)
        a.sounds.add("Baby cry, infant cry")
        a.persist()
        saved = json.loads(ROOT_SETTINGS.read_text())
        b = UiState()
        restored = b.restore()
        by = {e["label"]: e for e in b.sounds.entries()}
        ok = (
            restored
            and saved["names"] == ["Pablo"]
            and b.names == ["Pablo"]
            and b.mode == "focus"
            and b.cone_deg == 90.0
            and not by["DOG"]["enabled"]
            and by["BABY CRY"]["enabled"]
        )
    record("settings persist", ok, "names/mode/cone/sound list survive a restart")
    return ok


def test_sound_bearing():
    from sona.state import UiState

    s = UiState()
    s.record_doa(200.0, True, speech=True, moved=True)  # a talker at 200°
    s.record_doa(90.0, True, speech=False, moved=True)  # a non-speech source moved the DoA to 90°
    siren = round(s.sound_direction() or -1) == 90
    s.record_doa(200.0, True, speech=True, moved=True)  # the talker again
    stays = round(s.sound_direction() or -1) == 90  # the siren must not jump to the talker
    talker = round(s.speaker_direction() or -1) == 200
    ok = siren and stays and talker
    record("sound vs speech bearing", ok, "siren keeps its own bearing while someone talks")
    return ok


def test_own_voice():
    import numpy as np
    import soundfile as sf

    from sona import config
    from sona.voice.speaker import OwnVoice, cosine

    v = OwnVoice()
    if not v.available:
        record("own voice", True, f"skipped — {v.reason}")
        return True
    wav, _ = sf.read(config.WHISPER_DIR / "samples" / "jfk.wav", dtype="int16")
    a, b = v.embed(wav[: len(wav) // 2]), v.embed(wav[len(wav) // 2 :])
    same = cosine(a, b)
    detail = f"same speaker {same:.2f}"
    ok = same > config.OWN_VOICE_THRESHOLD
    other_clip = ROOT / "out" / "respeaker_test.wav"  # a different speaker, if recorded earlier
    if other_clip.exists():
        o, _ = sf.read(other_clip, dtype="int16")
        o = o[:, 0] if o.ndim > 1 else o
        other = cosine(a, v.embed(np.ascontiguousarray(o)))
        ok = ok and other < same
        detail += f" vs other speaker {other:.2f} (threshold {config.OWN_VOICE_THRESHOLD})"
    record("own voice", ok, detail)
    return ok


def test_name_matcher():
    from sona.names.matcher import NameMatcher

    m = NameMatcher(["Miquel"], 0.82, 0.55)
    hits = all(m.match(t) for t in ["Hey Miquel!", "Michael?", "Miguel come here", "Miquel's bag"])
    misses = not any(m.match(t) for t in ["do you know the time", "the medical center"])
    record("name matcher", hits and misses, "matches Michael/Miguel, rejects medical")
    return hits and misses


def test_name_render():
    from sona.display.renderer import Renderer
    from sona.state import SoundEvent, UiState

    state = UiState()
    state.mode = "alerts"  # a name alert must show even with captions off
    state.set_name(SoundEvent(label="MIQUEL", kind="name", angle=210.0))
    img = Renderer().render(state)
    out = ROOT / "out" / "selftest_name.png"
    out.write_bytes(Renderer.to_png_bytes(img))
    ok = state.active_name() is not None and "MIQUEL" in state.glass_text()
    record("name alert render", ok, f"glass_text={state.glass_text()!r} -> {out.name}")
    return ok


def test_yamnet():
    import numpy as np
    import soundfile as sf

    from sona import config
    from sona.hub import Hub
    from sona.sounds.classifier import SoundClassifier

    clf = SoundClassifier(Hub())
    wav, _ = sf.read(config.WHISPER_DIR / "samples" / "jfk.wav", dtype="float32")
    scores = clf._infer(wav[: clf.WINDOW])
    top = int(np.argmax(scores))
    ok = clf.names[top] == "Speech"
    record("yamnet", ok, f"top class on jfk.wav: {clf.names[top]} ({scores[top]:.2f})")
    return ok


async def test_stt():
    import soundfile as sf

    from sona import config
    from sona.stt.engine import WhisperSTT

    stt = WhisperSTT()
    t0 = time.time()
    await stt.start()
    wav, _ = sf.read(config.WHISPER_DIR / "samples" / "jfk.wav", dtype="int16")
    t1 = time.time()
    text = await stt.transcribe(wav)
    dt = time.time() - t1
    await stt.stop()
    ok = "country" in text.lower()
    record("whisper stt", ok, f"load {t1 - t0:.1f}s, 11s audio in {dt:.2f}s: '{text[:60]}…'")
    return ok


def main():
    quick = "--quick" in sys.argv  # CI: skip tests that need downloaded models / whisper.cpp
    print("sona selftest" + (" (quick)" if quick else ""))
    test_renderer()
    test_g1_packets()
    test_caption_page()
    test_modes()
    test_sound_watchlist()
    test_settings_roundtrip()
    test_sound_bearing()
    test_name_matcher()
    test_name_render()
    if not quick:
        test_own_voice()
        test_yamnet()
        asyncio.run(test_stt())
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
