"""Tests for ``core.asr`` — dispatcher and single-track pass-through."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

# Import core.pipeline first so sources/__init__.py finishes loading
# before the individual speech-source modules are pulled in — matches
# the order in test_pipeline_stage_callback.py and avoids the partial-
# init circular import error.
from core.pipeline import run as _  # noqa: F401

from core.asr import make_source, transcribe_one_track
from domain.annotations import SpeechSegment
from sources.base import Source
from sources.speech.faster_whisper import FasterWhisperSource
from sources.speech.gigaam import GigaAMSource


class _FakeSource(Source):
    """Source stub that records the args passed to transcribe_track."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def extract(self, session_dir: Path) -> list:
        raise NotImplementedError("not called in these tests")

    def transcribe_track(
        self,
        audio_path: Path,
        speaker: str | None = None,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[SpeechSegment]:
        self.calls.append({
            "audio_path": audio_path,
            "speaker": speaker,
            "on_progress": on_progress,
            "should_cancel": should_cancel,
        })
        # Echo a single segment so pass-through assertions can verify
        # the return value rides all the way back.
        seg = SpeechSegment(
            start=0.0,
            end=1.0,
            speaker=speaker or "unknown",
            text="hello",
            confidence=0.9,
        )
        if on_progress is not None:
            on_progress(0.5)
            on_progress(1.0)
        return [seg]


# ── make_source dispatch ─────────────────────────────────────────────


def test_make_source_gigaam() -> None:
    src = make_source("gigaam")
    assert isinstance(src, GigaAMSource)


@pytest.mark.parametrize("model_id", ["faster-whisper", "whisper", "whisper-lg", "whisper-med"])
def test_make_source_whisper_family(model_id: str) -> None:
    src = make_source(model_id)
    assert isinstance(src, FasterWhisperSource)


def test_make_source_passes_device_and_language() -> None:
    src = make_source("faster-whisper", device="cpu", language="en")
    assert isinstance(src, FasterWhisperSource)
    assert src.device == "cpu"
    assert src.language == "en"


def test_make_source_raises_on_unknown_id() -> None:
    with pytest.raises(ValueError, match="unknown ASR model_id"):
        make_source("not-a-model")


# ── transcribe_one_track pass-through ────────────────────────────────


def test_transcribe_one_track_forwards_args(tmp_path: Path) -> None:
    src = _FakeSource()
    audio = tmp_path / "x.flac"
    audio.write_bytes(b"")

    captured_progress: list[float] = []
    should_cancel = lambda: False  # noqa: E731

    segs = transcribe_one_track(
        src,
        audio,
        speaker="Andrey",
        on_progress=captured_progress.append,
        should_cancel=should_cancel,
    )

    assert len(src.calls) == 1
    call = src.calls[0]
    assert call["audio_path"] == audio
    assert call["speaker"] == "Andrey"
    assert call["should_cancel"] is should_cancel
    # on_progress was invoked by the fake source; we recorded both ticks.
    assert captured_progress == [0.5, 1.0]
    assert len(segs) == 1
    assert segs[0].speaker == "Andrey"
    assert segs[0].text == "hello"
