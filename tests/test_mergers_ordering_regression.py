"""Regression: a mis-anchored ASR segment must not invert dialogue.

Derived from a real failure in the Азланти campaign (session recorded
2026-03-28, ~4h17m in). WhisperX emitted a 27.8-second segment that
glued two phrases separated by a 4-second pause, and its forced
aligner stretched the leading function word across 13.67 seconds —
from the VAD window edge to where the speaker actually started. The
segment's nominal ``start`` therefore preceded four replies from the
other speaker that in reality came *before* it.

``ScriptMerger`` sorts on ``SpeechSegment.start``, so it faithfully
placed an answer ahead of the question that prompted it. In the
original scene that put a secret's reveal before the question that
drew it out, and the follow-up realisation then read as unprompted —
the scene became incoherent for a downstream LLM.

Numbers here mirror the real segment exactly; the dialogue is
synthetic (the repository is public and the source is a private
session recording).

Timeline of what was actually said:

    15743.7  B: "So you have been everywhere?"
    15752.7  B: "Fascinating."                    ┐
    15753.8  B: "You are well travelled."         │ four replies that
    15757.0  B: "You have seen much."             │ precede A's answer
    15758.7  B: "And where is your friend?"       ┘
    15763.6  A: "...he smiles and raises a finger" ← real onset
    15774.5  A: "this will be our secret"
    15778.9  B: "Oh — you are the sword!"

But the aligner labelled A's segment as starting at 15749.354.
"""

from __future__ import annotations

import pytest

from domain.annotations import SpeechSegment
from domain.timeline import Timeline
from mergers.script_merger import ScriptMerger

#: Nominal start the aligner produced for speaker A's segment.
MISANCHORED_START = 15749.354
#: Where A's first real word begins. 13.67 s later.
TRUE_ONSET = 15763.584
#: End of A's segment — after every one of B's four replies.
A_END = 15777.174


def _seg(start: float, end: float, speaker: str, text: str) -> SpeechSegment:
    return SpeechSegment(start=start, end=end, speaker=speaker, text=text)


def _scene(a_start: float) -> Timeline:
    """The scene with speaker A's segment anchored at ``a_start``."""
    return Timeline(
        speech=[
            _seg(15743.700, 15748.100, "B", "So you have been everywhere?"),
            _seg(15752.725, 15753.807, "B", "Fascinating."),
            _seg(15753.847, 15757.011, "B", "You are well travelled."),
            _seg(15757.031, 15758.633, "B", "You have seen much."),
            _seg(15758.693, 15759.554, "B", "And where is your friend?"),
            _seg(a_start, A_END, "A", "this will be our secret"),
            _seg(15778.922, 15782.166, "B", "Oh - you are the sword!"),
        ],
        emotions=[],
        chat=[],
        game_log=[],
    )


def _order(events) -> list[str]:
    """Speaker sequence of the merged script."""
    return [e.speaker for e in events]


def test_true_onset_yields_coherent_order():
    """With a correct anchor the exchange reads question -> answer.

    This is the control: it pins down what the merger *should*
    produce, independent of the anchoring defect.
    """

    events = ScriptMerger().merge(_scene(TRUE_ONSET))

    # B's opener sits 4.6 s before the rest of his run — past the 1.0 s
    # merge gap — so it stays its own block: opener, run, answer,
    # reaction. What matters is that A lands between the question and
    # the reaction.
    assert _order(events) == ["B", "B", "A", "B"], _order(events)

    answer_idx = next(i for i, e in enumerate(events) if e.speaker == "A")
    question = events[answer_idx - 1]
    assert "where is your friend" in question.text
    reaction = events[answer_idx + 1]
    assert "you are the sword" in reaction.text.lower()


@pytest.mark.xfail(
    reason=(
        "Known defect: ScriptMerger anchors on SpeechSegment.start, so a "
        "mis-aligned segment jumps ahead of replies that preceded it. Fixing "
        "it needs either word-level onsets (WhisperX carries them) or "
        "splitting segments on long internal pauses. Tracked for the merger "
        "rework; the VAD-sliced GigaAM path may not exhibit it at all."
    ),
    strict=True,
)
def test_misanchored_segment_must_not_jump_the_queue():
    """The real, failing case — answer must stay after the question."""

    events = ScriptMerger().merge(_scene(MISANCHORED_START))

    answer_idx = next(i for i, e in enumerate(events) if e.speaker == "A")
    preceding = " ".join(e.text for e in events[:answer_idx])
    assert "where is your friend" in preceding, (
        "A's answer was placed before B's question — dialogue inverted. "
        f"Order: {_order(events)}"
    )


def test_defect_is_a_pure_anchoring_artefact():
    """Same words, same speakers — only the anchor differs.

    Guards the diagnosis itself: if this ever stops holding, the two
    tests above are measuring something other than the anchor.
    """

    good = ScriptMerger().merge(_scene(TRUE_ONSET))
    bad = ScriptMerger().merge(_scene(MISANCHORED_START))

    assert {e.speaker for e in good} == {e.speaker for e in bad}
    assert sum(len(e.text) for e in good) == sum(len(e.text) for e in bad)
    assert _order(good) != _order(bad), (
        "anchoring made no difference — the fixture no longer reproduces "
        "the defect"
    )
