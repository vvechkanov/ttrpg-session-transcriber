"""Integration test: full pipeline from folder-open to merged.txt on disk.

Exercises the complete happy-path wiring:

    openSession() -> tracks loaded -> runAsr() -> merged.txt written

and the failure path:

    runAsr() with unwritable session_dir -> phase == "failed"

No real ASR model is needed — ``core.asr.make_source`` is replaced by
``monkeypatch`` with a ``_FakeSource`` that returns scripted
``SpeechSegment`` objects synchronously.  The merger is real
(``ScriptMerger`` + ``PlainTextRenderer``) so we actually test I/O.
"""

from __future__ import annotations

import os
import sys
import stat
from pathlib import Path
from typing import Callable

import pytest

# Headless Qt — must be set before PySide6 imports.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Warm sources/__init__ before deep Qt-model imports (avoids circular
# import seen in other test modules — same pattern as asr_worker test).
from core.pipeline import run as _  # noqa: F401

from PySide6.QtGui import QGuiApplication

from domain.annotations import SpeechSegment
from sources.base import Source
from ui.engines import PipelineController
from ui.models import AppModel, ModelRegistry, SessionMeta, SourceListModel, TrackListModel


# ---------------------------------------------------------------------------
# Shared QGuiApplication — one instance per process.
# ---------------------------------------------------------------------------

def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("integration-test")
    app.setOrganizationName("integration-test")
    return app


# ---------------------------------------------------------------------------
# Fake ASR source — reusable across both test cases in this module.
# ---------------------------------------------------------------------------

class _FakeSource(Source):
    """Returns two scripted SpeechSegments without touching any audio file."""

    name = "fake-integration"

    def extract(self, session_dir: Path) -> list:
        raise NotImplementedError("not used in these tests")

    def transcribe_track(
        self,
        audio_path: Path,
        speaker: str | None = None,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[SpeechSegment]:
        # Report progress so PipelineController can see the worker run.
        for pct in (0.5, 1.0):
            if should_cancel is not None and should_cancel():
                return []
            if on_progress is not None:
                on_progress(pct)
        speaker_name = speaker or audio_path.stem
        return [
            SpeechSegment(
                start=0.0,
                end=1.0,
                speaker=speaker_name,
                text=f"hello from {speaker_name}",
                confidence=None,
            ),
            SpeechSegment(
                start=1.5,
                end=2.5,
                speaker=speaker_name,
                text=f"second line {speaker_name}",
                confidence=None,
            ),
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_pipeline(app_model, tracks_model, session_meta):
    """Wire up a PipelineController the same way app_qml.main() does."""
    model_registry = ModelRegistry()
    pipeline = PipelineController(app_model, tracks_model, session_meta, model_registry)
    session_meta.sessionOpened.connect(tracks_model.loadFromDir)
    session_meta.sessionOpened.connect(SourceListModel().loadFromDir)
    return pipeline


# ---------------------------------------------------------------------------
# Happy-path test
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_full_pipeline_writes_merged_txt(
    qtbot,
    two_track_session,
    monkeypatch,
):
    """openSession → 2 tracks loaded → runAsr() → merged.txt with fake text."""
    _ensure_app()

    session_dir, track_paths = two_track_session

    # Replace make_source so no real model is loaded.
    fake_source = _FakeSource()
    monkeypatch.setattr("core.asr.make_source", lambda model_id, **kw: fake_source)
    # Also patch the reference inside pipeline_controller which imports it directly.
    monkeypatch.setattr(
        "ui.engines.pipeline_controller.make_source",
        lambda model_id, **kw: fake_source,
    )

    app_model = AppModel()
    tracks_model = TrackListModel()
    session_meta = SessionMeta()
    pipeline = _build_pipeline(app_model, tracks_model, session_meta)

    # Open the session — this calls loadFromDir on tracks_model.
    session_meta.openSession(str(session_dir))

    # Verify that both .wav files were discovered.
    assert tracks_model.rowCount() == 2, (
        f"Expected 2 tracks after openSession, got {tracks_model.rowCount()}"
    )

    # Kick off the pipeline and wait for the finished signal.
    with qtbot.waitSignal(pipeline.finished, timeout=10_000):
        pipeline.runAsr()

    # ── Post-run assertions ──────────────────────────────────────────────
    merged_txt = session_dir / "merged.txt"
    assert merged_txt.exists(), "merged.txt was not created"
    content = merged_txt.read_text(encoding="utf-8")
    assert content.strip(), "merged.txt is empty"

    # Each track contributed two segments; both speakers' text must appear.
    assert "hello from" in content, f"Expected 'hello from' in merged.txt; got:\n{content}"
    assert "second line" in content, f"Expected 'second line' in merged.txt; got:\n{content}"

    # Phase must be "done" and summary must be populated.
    assert app_model.phase == "done", f"Expected phase='done', got {app_model.phase!r}"
    summary = app_model.doneSummary
    assert summary, "doneSummary is empty after successful run"
    assert "wordCount" in summary, f"doneSummary missing 'wordCount' key: {summary}"
    assert "cueCount" in summary, f"doneSummary missing 'cueCount' key: {summary}"

    # outputPath property must point to the file.
    assert pipeline.outputPath == str(merged_txt), (
        f"outputPath mismatch: {pipeline.outputPath!r} != {str(merged_txt)!r}"
    )


# ---------------------------------------------------------------------------
# Failure-path test — unwritable session dir
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_pipeline_failed_phase_on_unwritable_dir(
    qtbot,
    two_track_session,
    monkeypatch,
):
    """When merged.txt cannot be written, phase must flip to 'failed'."""
    _ensure_app()

    session_dir, _track_paths = two_track_session

    fake_source = _FakeSource()
    monkeypatch.setattr("core.asr.make_source", lambda model_id, **kw: fake_source)
    monkeypatch.setattr(
        "ui.engines.pipeline_controller.make_source",
        lambda model_id, **kw: fake_source,
    )

    app_model = AppModel()
    tracks_model = TrackListModel()
    session_meta = SessionMeta()
    pipeline = _build_pipeline(app_model, tracks_model, session_meta)

    session_meta.openSession(str(session_dir))
    assert tracks_model.rowCount() == 2

    # Make the session directory read-only so write_bytes() raises PermissionError.
    # We restore permissions in a finalizer so pytest can clean up tmp_path.
    original_mode = session_dir.stat().st_mode
    try:
        # On Windows, removing the write bit makes the directory read-only.
        session_dir.chmod(stat.S_IREAD | stat.S_IEXEC)
        # Verify the directory is actually not writable now; if the OS
        # (e.g. running as Administrator) ignores the chmod, skip the test.
        test_file = session_dir / "_write_check"
        try:
            test_file.write_bytes(b"x")
            test_file.unlink()
            pytest.skip(
                "Cannot make directory read-only on this OS/user — "
                "skipping write-failure path test"
            )
        except (PermissionError, OSError):
            pass  # Good — writes are blocked as expected.

        with qtbot.waitSignal(pipeline.finished, timeout=10_000):
            pipeline.runAsr()

    finally:
        # Always restore so pytest can delete the tmp directory.
        try:
            session_dir.chmod(original_mode)
        except Exception:
            pass

    assert app_model.phase == "failed", (
        f"Expected phase='failed' after write error, got {app_model.phase!r}"
    )
    assert app_model.errorMessage, (
        "errorMessage must be non-empty when phase is 'failed'"
    )


# ---------------------------------------------------------------------------
# Edge-case: no session open → runAsr() must still reach "failed" phase
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_pipeline_failed_when_no_session_open(qtbot, monkeypatch):
    """runAsr() without an open session must produce phase='failed'."""
    _ensure_app()

    fake_source = _FakeSource()
    monkeypatch.setattr("core.asr.make_source", lambda model_id, **kw: fake_source)
    monkeypatch.setattr(
        "ui.engines.pipeline_controller.make_source",
        lambda model_id, **kw: fake_source,
    )

    app_model = AppModel()
    tracks_model = TrackListModel()
    session_meta = SessionMeta()
    pipeline = _build_pipeline(app_model, tracks_model, session_meta)

    # No openSession call — tracks_model is empty, session_meta has no dir.
    # With an empty queue the controller goes straight to _spawn_merger,
    # which surfaces "Сессия не выбрана" and flips to failed.
    with qtbot.waitSignal(pipeline.finished, timeout=5_000):
        pipeline.runAsr()

    assert app_model.phase == "failed", (
        f"Expected phase='failed' with no session, got {app_model.phase!r}"
    )
    assert app_model.errorMessage, (
        "errorMessage must be non-empty when no session is open"
    )
