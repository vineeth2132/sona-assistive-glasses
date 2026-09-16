"""Caption post-processing: cleanup + hallucination gating.

Whisper reliably hallucinates YouTube-outro phrases ("Thanks for watching.",
"Thank you.", "you") on segments that are mostly noise. We gate with YAMNet's live
Speech score: if the classifier barely heard speech, whisper's output is not trusted.

Stretch goal (post-Friday): route long utterances through a small local model
(llama.cpp + Qwen2.5-0.5B/1.5B-Instruct Q4 on the Pi 5) to compress them.
"""

from .. import config

# Nearly always fabricated, regardless of context:
ALWAYS_DROP = {
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "subtitles by the amara.org community",
}

# Fabricated *when the classifier barely heard speech*:
SUSPECT = {
    "you",
    "thank you",
    "thanks",
    "okay",
    "ok",
    "so",
    "oh",
    "bye",
    "hmm",
    "i'm sorry",
    "yeah",
    "uh",
    "um",
    "the",
}


def refine(text: str) -> str:
    text = " ".join(text.split())
    # whisper emits bracketed non-speech artifacts, e.g. [BLANK_AUDIO], (wind blowing)
    if text.startswith("[") and text.endswith("]"):
        return ""
    if text.startswith("(") and text.endswith(")"):
        return ""
    return text


def accept(text: str, speech_score: float | None) -> str | None:
    """Final say on whether a transcribed utterance becomes a caption."""
    if not text:
        return None
    norm = text.lower().strip(" .,!?…-")
    if len(norm) <= 1 or norm in ALWAYS_DROP:  # lone "I"/"a" from a clipped fragment
        return None
    if speech_score is not None:
        if speech_score < config.SPEECH_GATE_MIN:
            return None
        if norm in SUSPECT and speech_score < config.SPEECH_GATE_SUSPECT:
            return None
    return text
