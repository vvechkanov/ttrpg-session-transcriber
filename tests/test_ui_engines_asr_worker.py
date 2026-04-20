"""Tests for ``ui.engines.asr_worker.AsrWorker``.

Uses a fake Source so the test doesn't need the 3 GB faster-whisper
bundle or the GigaAM install. pytest-qt's ``qtbot`` is the standard
test harness for signal assertions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

# Import core.pipeline first to avoid a circular import between
# sources/__init__.py and core/pipeline.py — the established order
# elsewhere in the test suite (see test_pipeline_stage_callback).
from core.pipeline import run as _  # noqa: F401

from PySide6.QtCore import QThread

from domain.annotations import SpeechSegment
from sources.base import Source
from ui.engines.asr_worker import AsrWorker


class _FakeSource(Source):
    """Emits a scripted progress sequence; never raises on success."""

    name = "fake"

    def __init__(
        self,
        *,
        raises: Exception | None = None,
        progress_ticks: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0),
    ) -> None:
        self._raises = raises
        self._ticks = progress_ticks
        self.called = False

    def extract(self, session_dir: Path) -> list:
        raise NotImplementedError

    def transcribe_track(
        self,
        audio_path: Path,
        speaker: str | None = None,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[SpeechSegment]:
        self.called = True
        if self._raises is not None:
            raise self._raises
        for tick in self._ticks:
            if should_cancel is not None and should_cancel():
                return []
            if on_progress is not None:
                on_progress(tick)
        return [SpeechSegment(start=0.0, end=1.0, speaker=speaker or "x", text="hi", confidence=None)]


def _run_on_thread(qtbot, worker: AsrWorker) -> None:
    """Move the worker onto a QThread, start it, wait for finished."""

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)

    thread.start()
    qtbot.waitUntil(lambda: not thread.isRunning(), timeout=5000)
    # deleteLater gets picked up once the event loop runs another tick;
    # for assertions we just need the signals already delivered.


def test_asr_worker_emits_progress_then_done(qtbot, tmp_path: Path) -> None:
    source = _FakeSource(progress_ticks=(0.1, 0.5, 1.0))
    worker = AsrWorker(row=3, source=source, audio_path=tmp_path / "x.flac")

    progress_seen: list[tuple[int, float]] = []
    done_seen: list[tuple[int, list]] = []
    error_seen: list[tuple[int, str]] = []

    worker.progress.connect(lambda row, pct: progress_seen.append((row, pct)))
    worker.done.connect(lambda row, segs: done_seen.append((row, segs)))
    worker.error.connect(lambda row, msg: error_seen.append((row, msg)))

    _run_on_thread(qtbot, worker)

    assert source.called
    # Progress emissions are queued through the worker thread; all three
    # should have been delivered before finished ran.
    assert [p for _, p in progress_seen] == [0.1, 0.5, 1.0]
    assert len(done_seen) == 1
    row, segs = done_seen[0]
    assert row == 3
    # FakeSource returns one segment (see its transcribe_track impl).
    assert len(segs) == 1
    assert segs[0].text == "hi"
    assert error_seen == []


def test_asr_worker_emits_error_on_exception(qtbot, tmp_path: Path) -> None:
    source = _FakeSource(raises=RuntimeError("model not installed"))
    worker = AsrWorker(row=7, source=source, audio_path=tmp_path / "x.flac")

    done_seen: list[tuple[int, list]] = []
    error_seen: list[tuple[int, str]] = []

    worker.done.connect(lambda row, segs: done_seen.append((row, segs)))
    worker.error.connect(lambda row, msg: error_seen.append((row, msg)))

    _run_on_thread(qtbot, worker)

    assert done_seen == []
    assert error_seen == [(7, "model not installed")]


def test_asr_worker_respects_cancel_flag(qtbot, tmp_path: Path) -> None:
    source = _FakeSource(progress_ticks=(0.1, 0.2, 0.3, 0.4))
    worker = AsrWorker(row=2, source=source, audio_path=tmp_path / "x.flac")

    progress_seen: list[float] = []
    done_seen: list[tuple[int, list]] = []

    worker.progress.connect(lambda _r, p: progress_seen.append(p))
    worker.done.connect(lambda row, segs: done_seen.append((row, segs)))

    # Cancel BEFORE starting — fake source's loop will see should_cancel
    # return True on the very first iteration and bail with no ticks.
    worker.cancel()

    _run_on_thread(qtbot, worker)

    assert progress_seen == []
    assert done_seen == []  # no done emission when cancelled
