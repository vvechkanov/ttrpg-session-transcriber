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
    """merged.txt format follows the setting, and never dies for it.

    Every case here runs the worker. The first version of this class
    asserted on ``worker._renderer_name`` and re-implemented the
    fallback inline — so it stayed green while the real fallback raised
    NameError, killed the merge and wrote no file at all.
    """

    def _run(self, session_dir, **kwargs):
        from domain.annotations import SpeechSegment
        from ui.engines.merger_worker import MergerWorker

        worker = MergerWorker(
            session_dir=session_dir,
            speech_segments=[
                SpeechSegment(start=0.0, end=1.0, speaker="Вова", text="да")
            ],
            **kwargs,
        )
        errors: list[str] = []
        worker.error.connect(errors.append)
        worker.run()
        return errors, session_dir / "merged.txt"

    def test_default_is_the_historical_format(self, tmp_path):
        errors, merged = self._run(tmp_path)
        assert not errors
        assert merged.read_text(encoding="utf-8").startswith("Вова: да")

    def test_named_renderer_reaches_the_output(self, tmp_path):
        """combat-aware on a fight-less session equals plain-text."""
        errors, merged = self._run(tmp_path, renderer_name="combat-aware")
        assert not errors
        assert merged.read_text(encoding="utf-8").startswith("Вова: да")

    def test_unknown_renderer_still_writes_the_transcript(self, tmp_path, caplog):
        """A stale setting must not destroy a finished merge.

        The name is persisted in QSettings and outlives the code that
        knew it. This exact path used to raise NameError — the warning
        it logs referenced a logger the module never defined — and the
        transcript was lost over the choice of output format.
        """
        errors, merged = self._run(tmp_path, renderer_name="renderer-that-was-removed")

        assert not errors, f"the merge died over a format name: {errors}"
        assert merged.exists(), "merged.txt was not written"
        assert merged.read_text(encoding="utf-8").startswith("Вова: да")

    def test_unknown_renderer_says_so_in_the_log(self, tmp_path, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="ui.engines.merger_worker"):
            self._run(tmp_path, renderer_name="nope")

        assert any("nope" in r.getMessage() for r in caplog.records), (
            "a silent substitution of the output format is still a surprise"
        )


class TestSessionClockReachesTheOutput:
    """The GUI path must compute wall-clock time, not just be able to.

    Timeline.recording_start is what turns relative offsets into the
    hours the players saw. core.pipeline computed it — but the GUI
    never goes through core.pipeline, it goes through this worker, and
    the worker built its Timeline without it. So the renderer that
    prints clock times printed none, and no test noticed: they all
    stamped wall_clock by hand.
    """

    _FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tz_late_start"

    def _session(self, tmp_path):
        import shutil

        session = tmp_path / "s"
        session.mkdir()
        shutil.copy(self._FIXTURE / "combat.json", session / "Бой.txt")
        shutil.copy(
            self._FIXTURE / "fvtt-log-fixture.txt", session / "fvtt-log-s.txt"
        )
        # Start the recording before the fight so nothing is dropped.
        (session / "info.txt").write_text(
            "Start time: 2026-08-15T17:00:00Z\n", encoding="utf-8"
        )
        return session

    def _merged(self, tmp_path, renderer_name):
        from domain.annotations import SpeechSegment
        from ui.engines.merger_worker import MergerWorker

        session = self._session(tmp_path)
        worker = MergerWorker(
            session_dir=session,
            speech_segments=[
                SpeechSegment(start=800.0, end=802.0, speaker="Вова", text="кидай")
            ],
            chat_log_path=session / "fvtt-log-s.txt",
            combat_log_paths=[session / "Бой.txt"],
            renderer_name=renderer_name,
        )
        errors: list[str] = []
        worker.error.connect(errors.append)
        worker.run()
        assert not errors, errors
        return (session / "merged.txt").read_text(encoding="utf-8")

    def test_combat_header_carries_the_session_clock(self, tmp_path, pin_system_tz):
        pin_system_tz(2.0)
        out = self._merged(tmp_path, "combat-aware")
        # The fight ran 19:11–20:18 in the session's own +02:00.
        assert "[19:11 – 20:18]" in out, (
            "no wall-clock span — the worker built a Timeline with no "
            "recording_start, so nothing was ever stamped"
        )

    def test_lines_inside_the_fight_are_timed(self, tmp_path, pin_system_tz):
        pin_system_tz(2.0)
        out = self._merged(tmp_path, "combat-aware")
        stamped = [ln for ln in out.splitlines() if ln.startswith("  [")]
        assert stamped, "not a single timed line inside the fight"

    def test_plain_text_output_is_unaffected(self, tmp_path, pin_system_tz):
        """Stamping must not change the historical format."""
        pin_system_tz(2.0)
        out = self._merged(tmp_path, "plain-text")
        assert "Вова: кидай" in out
        assert "[19:11" not in out
