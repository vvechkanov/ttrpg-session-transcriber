"""Tests for ``ui.engines.merger_worker.MergerWorker``.

Real ScriptMerger + PlainTextRenderer — no ML needed. Speech
segments are fabricated as plain SpeechSegment dataclasses, chat
logs are left empty since fvtt parsing is exercised by
``tests/test_sources_fvtt.py``.
"""

from __future__ import annotations

from pathlib import Path

# Import core.pipeline first to warm sources/__init__ (see
# test_pipeline_stage_callback.py for the rationale).
from core.pipeline import run as _  # noqa: F401

from PySide6.QtCore import QThread

from domain.annotations import SpeechSegment
from ui.engines.merger_worker import MergerWorker


def _run_on_thread(qtbot, worker: MergerWorker) -> None:
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    thread.start()
    qtbot.waitUntil(lambda: not thread.isRunning(), timeout=5000)


def test_merger_writes_merged_txt(qtbot, tmp_path: Path) -> None:
    session = tmp_path / "session-1"
    session.mkdir()

    speech = [
        SpeechSegment(start=0.0, end=2.0, speaker="Andrey", text="hello world", confidence=None),
        SpeechSegment(start=3.0, end=5.0, speaker="Boris",  text="greetings",   confidence=None),
    ]

    worker = MergerWorker(
        session_dir=session,
        speech_segments=speech,
        chat_log_path=None,
        total_duration=60.0,
    )

    progress: list[float] = []
    done: list[str] = []
    errors: list[str] = []

    worker.progress.connect(progress.append)
    worker.done.connect(done.append)
    worker.error.connect(errors.append)

    _run_on_thread(qtbot, worker)

    assert errors == [], f"unexpected errors: {errors}"
    assert len(done) == 1
    output_path = Path(done[0])
    assert output_path == session / "merged.txt"
    assert output_path.exists()

    # Payload contains both speakers' text in Cyrillic-clean UTF-8.
    text = output_path.read_text(encoding="utf-8")
    assert "Andrey" in text
    assert "Boris" in text
    assert "hello world" in text
    assert "greetings" in text

    # Progress emitted monotonically from 0 to 1.
    assert progress[0] == 0.0
    assert progress[-1] == 1.0
    assert progress == sorted(progress)


def test_merger_no_speech_still_writes_empty_file(qtbot, tmp_path: Path) -> None:
    session = tmp_path / "session-empty"
    session.mkdir()

    worker = MergerWorker(
        session_dir=session,
        speech_segments=[],
        chat_log_path=None,
        total_duration=0.0,
    )

    done: list[str] = []
    errors: list[str] = []
    worker.done.connect(done.append)
    worker.error.connect(errors.append)

    _run_on_thread(qtbot, worker)

    assert errors == []
    assert len(done) == 1
    assert Path(done[0]).exists()


def test_merger_cancel_before_run_short_circuits(qtbot, tmp_path: Path) -> None:
    session = tmp_path / "session-cancel"
    session.mkdir()

    worker = MergerWorker(
        session_dir=session,
        speech_segments=[],
        chat_log_path=None,
        total_duration=0.0,
    )

    done: list[str] = []
    errors: list[str] = []
    worker.done.connect(done.append)
    worker.error.connect(errors.append)

    worker.cancel()
    _run_on_thread(qtbot, worker)

    # Cancelled before write completed — no done emission, no file.
    assert done == []
    assert errors == []
    assert not (session / "merged.txt").exists()


class TestRendererSelection:
    """merged.txt format follows the setting, and never dies for it."""

    def _events(self):
        from domain.events import SpeechEvent
        return [SpeechEvent(start=0.0, end=1.0, speaker="Вова", text="да")]

    def test_default_is_the_historical_format(self, tmp_path):
        from ui.engines.merger_worker import MergerWorker
        worker = MergerWorker(session_dir=tmp_path, speech_segments=[])
        assert worker._renderer_name == "plain-text"

    def test_named_renderer_is_used(self, tmp_path):
        from renderers import RENDERERS
        from ui.engines.merger_worker import MergerWorker

        worker = MergerWorker(
            session_dir=tmp_path, speech_segments=[], renderer_name="combat-aware"
        )
        assert worker._renderer_name == "combat-aware"
        assert "combat-aware" in RENDERERS

    def test_unknown_renderer_falls_back_instead_of_failing(self, tmp_path, caplog):
        """A stale setting must not destroy a finished transcript.

        The name is persisted in QSettings and outlives the code that
        knew it. Raising here would throw away a merge that had already
        succeeded, over the choice of output format.
        """
        from renderers import RENDERERS

        name = "renderer-that-was-removed"
        assert name not in RENDERERS

        chosen = RENDERERS.get(name) or RENDERERS["plain-text"]
        payload = chosen().render(self._events())
        assert b"\xd0\x92\xd0\xbe\xd0\xb2\xd0\xb0" in payload  # "Вова"
