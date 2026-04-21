"""Multi-segment ASR worker tests — feature #4 iteration 4b.

Exercises the row-level fanout: one :class:`AsrWorker` runs ASR over
N :class:`SegmentJob`\\ s, concatenates the shifted results, and
forwards progress as a duration-weighted 0..1 stream.

These tests do not spin up a real QThread — we call ``worker.run()``
inline on the main thread, so ``QThread.currentThread()`` inside
``run`` is simply the test thread and ``isInterruptionRequested``
stays ``False``. Cancellation is driven exclusively through
``worker.cancel()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

# Warm sources/__init__ so the AsrWorker's core.asr import chain
# finishes before its Qt parts instantiate.
from core.pipeline import run as _  # noqa: F401

from PySide6.QtGui import QGuiApplication

from domain.annotations import SpeechSegment
from sources.base import Source
from ui.engines.asr_worker import AsrWorker, SegmentJob


def _app() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication([])


class _ScriptedSource(Source):
    """Deterministic source — returns a canned ``SpeechSegment`` list per call."""

    name = "scripted"

    def __init__(self, returns: list[list[SpeechSegment]]) -> None:
        self._returns = list(returns)
        self.calls: list[Path] = []

    def extract(self, session_dir: Path) -> list:
        raise NotImplementedError

    def transcribe_track(
        self,
        audio_path: Path,
        speaker: str | None = None,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[SpeechSegment]:
        self.calls.append(audio_path)
        # Report 0 → 1 progress so the worker's weighting shows up.
        if on_progress is not None:
            on_progress(0.0)
            on_progress(1.0)
        return self._returns.pop(0)


def _seg(start: float, end: float, text: str = "x") -> SpeechSegment:
    return SpeechSegment(start=start, end=end, speaker="p", text=text, confidence=None)


def test_two_segments_concatenated_with_offsets(tmp_path: Path) -> None:
    _app()

    audio_a = tmp_path / "a.flac"; audio_a.write_bytes(b"")
    audio_b = tmp_path / "b.flac"; audio_b.write_bytes(b"")

    source = _ScriptedSource(
        returns=[
            [_seg(0.0, 1.0, text="first-seg")],
            [_seg(0.0, 2.0, text="second-seg")],
        ]
    )

    worker = AsrWorker(
        0,
        source,
        (
            SegmentJob(audio_path=audio_a, offset_sec=0.0, duration_sec=1.0),
            SegmentJob(audio_path=audio_b, offset_sec=3600.0, duration_sec=2.0),
        ),
    )

    collected: list[tuple[int, list[SpeechSegment]]] = []
    worker.done.connect(lambda row, segs: collected.append((row, list(segs))))
    worker.run()

    assert source.calls == [audio_a, audio_b]
    assert len(collected) == 1
    row, segs = collected[0]
    assert row == 0
    assert len(segs) == 2
    # First segment unchanged.
    assert segs[0].text == "first-seg"
    assert segs[0].start == 0.0
    # Second segment shifted by offset_sec=3600.
    assert segs[1].text == "second-seg"
    assert segs[1].start == 3600.0
    assert segs[1].end == 3602.0


def test_progress_is_duration_weighted(tmp_path: Path) -> None:
    """Completing 2s of a 2+6s row should report ~25% progress."""

    _app()

    audio_a = tmp_path / "a.flac"; audio_a.write_bytes(b"")
    audio_b = tmp_path / "b.flac"; audio_b.write_bytes(b"")

    source = _ScriptedSource(
        returns=[[_seg(0.0, 1.0)], [_seg(0.0, 1.0)]]
    )

    worker = AsrWorker(
        0,
        source,
        (
            SegmentJob(audio_path=audio_a, duration_sec=2.0),
            SegmentJob(audio_path=audio_b, duration_sec=6.0),
        ),
    )

    progress_values: list[float] = []
    worker.progress.connect(lambda row, pct: progress_values.append(pct))
    worker.run()

    # First segment's on_progress(1.0) should yield base (0) + 1.0 * 0.25 = 0.25.
    assert pytest.approx(0.25, abs=1e-6) in [
        round(v, 6) for v in progress_values
    ]
    # Last tick of the second segment should be at 1.0.
    assert progress_values[-1] == pytest.approx(1.0)


def test_cancel_mid_row_skips_done_emission(tmp_path: Path) -> None:
    """cancel() after the first segment stops the loop before segment #2."""

    _app()

    audio_a = tmp_path / "a.flac"; audio_a.write_bytes(b"")
    audio_b = tmp_path / "b.flac"; audio_b.write_bytes(b"")

    # Second-segment return is a placeholder — we expect the loop to
    # exit before reaching it.
    source = _ScriptedSource(returns=[[_seg(0.0, 1.0)], [_seg(0.0, 1.0)]])

    worker = AsrWorker(
        0,
        source,
        (
            SegmentJob(audio_path=audio_a, duration_sec=1.0),
            SegmentJob(audio_path=audio_b, duration_sec=1.0),
        ),
    )

    # Flag cancel BEFORE run() executes so the first iteration sees it.
    worker.cancel()

    done_calls: list = []
    finished_calls: list = []
    worker.done.connect(lambda *a, **kw: done_calls.append(a))
    worker.finished.connect(lambda: finished_calls.append(True))
    worker.run()

    assert done_calls == []          # cancelled → no done signal
    assert finished_calls == [True]  # finished always fires exactly once
    assert source.calls == []        # first segment never invoked


def test_equal_weights_when_durations_unknown(tmp_path: Path) -> None:
    """Two 0-duration segments → 50/50 weighting so progress advances."""

    _app()

    audio_a = tmp_path / "a.flac"; audio_a.write_bytes(b"")
    audio_b = tmp_path / "b.flac"; audio_b.write_bytes(b"")

    source = _ScriptedSource(returns=[[_seg(0.0, 1.0)], [_seg(0.0, 1.0)]])

    worker = AsrWorker(
        0,
        source,
        (
            SegmentJob(audio_path=audio_a, duration_sec=0.0),
            SegmentJob(audio_path=audio_b, duration_sec=0.0),
        ),
    )

    progress: list[float] = []
    worker.progress.connect(lambda r, p: progress.append(p))
    worker.run()

    # Fake on_progress emits 0.0 and 1.0 per segment.
    # Seg A: base=0   w=0.5 → 0.0, 0.5
    # Seg B: base=0.5 w=0.5 → 0.5, 1.0
    assert pytest.approx(0.5, abs=1e-6) in [round(v, 6) for v in progress]
    assert progress[-1] == pytest.approx(1.0)


def test_legacy_path_accepts_raw_path(tmp_path: Path) -> None:
    """Passing a bare ``Path`` is wrapped in a single SegmentJob."""

    _app()

    audio = tmp_path / "a.flac"; audio.write_bytes(b"")
    source = _ScriptedSource(returns=[[_seg(5.0, 6.0, text="solo")]])

    worker = AsrWorker(0, source, audio)

    collected: list = []
    worker.done.connect(lambda row, segs: collected.append((row, list(segs))))
    worker.run()

    assert len(collected) == 1
    _, segs = collected[0]
    # No offset applied (zero-shift pass-through preserves timestamps).
    assert segs[0].start == 5.0
    assert segs[0].text == "solo"
