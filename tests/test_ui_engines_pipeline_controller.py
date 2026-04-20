"""Tests for ``ui.engines.pipeline_controller.PipelineController``.

Focuses on pieces that don't need a live QThread loop — summary
computation, state reset, cancellation flag. The full orchestration
(spawn worker → run → advance queue) is covered by the AsrWorker and
MergerWorker tests together with manual smoke via the boot harness.
"""

from __future__ import annotations

from pathlib import Path

# Warm sources/__init__ before any deep imports (see test_core_asr).
from core.pipeline import run as _  # noqa: F401

from PySide6.QtGui import QGuiApplication

import sys

from domain.annotations import SpeechSegment
from ui.engines.pipeline_controller import PipelineController, _format_bytes
from ui.models import AppModel, SessionMeta, TrackListModel


def _ensure_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("pc-test")
    app.setOrganizationName("pc-test")
    return app


def test_format_bytes_human_readable() -> None:
    assert _format_bytes(0) == "—"
    assert _format_bytes(-5) == "—"
    assert _format_bytes(512) == "512 B"
    assert _format_bytes(12 * 1024) == "12 KB"
    assert _format_bytes(int(1.5 * 1024 * 1024)) == "1.5 MB"


def test_compute_done_summary_reads_file_and_segments(tmp_path: Path) -> None:
    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    output = session / "merged.txt"
    output.write_text("Andrey: hello world\nBoris: greetings friend\n", encoding="utf-8")

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()

    # Pretend SessionMeta is pointing at our scratch session. Force
    # total_min via the openSession code path so the summary's hours-
    # and-minutes string has something to render.
    meta._total_min = 95  # 1 h 35 m
    meta._session_dir = session

    controller = PipelineController(app_model, tracks, meta)
    controller._collected_segments = {
        0: [
            SpeechSegment(start=0, end=1, speaker="Andrey", text="hello world", confidence=None),
        ],
        1: [
            SpeechSegment(start=2, end=3, speaker="Boris", text="greetings friend", confidence=None),
        ],
    }

    summary = controller._compute_done_summary(str(output))

    assert summary["fileSize"].endswith("B") or summary["fileSize"].endswith("KB")
    assert summary["wordCount"] == "6 слов"
    assert summary["cueCount"] == "2 реплик"
    assert summary["sessionLength"] == "1 ч 35 м"


def test_compute_done_summary_missing_file_gives_dashes(tmp_path: Path) -> None:
    _ensure_app()
    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    controller = PipelineController(app_model, tracks, meta)

    summary = controller._compute_done_summary(str(tmp_path / "nowhere.txt"))

    assert summary["fileSize"] == "—"
    assert summary["wordCount"] == "0 слов"
