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


class _StubChunkingPrefs:
    """Minimal stand-in for AppPreferences.build_chunking_options()."""

    def __init__(self, enabled: bool, chunk_chars: int = 40_000, overlap_ratio: float = 0.2) -> None:
        from core.chunking import ChunkingOptions
        self._opts = ChunkingOptions(
            enabled=enabled,
            chunk_chars=chunk_chars,
            overlap_ratio=overlap_ratio,
        )

    def build_chunking_options(self):
        return self._opts

    def build_asr_options(self):  # unused by these tests
        from core.asr import AsrOptions
        return AsrOptions()


def test_maybe_chunk_output_invokes_chunker_when_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    _ensure_app()

    calls: list[dict] = []

    def _fake_chunk(merged_path, **kwargs):
        dest = tmp_path / "chunks"
        dest.mkdir(exist_ok=True)
        calls.append({"merged": merged_path, **kwargs})
        return dest

    monkeypatch.setattr(
        "ui.engines.pipeline_controller.chunk_text_file", _fake_chunk
    )

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    prefs = _StubChunkingPrefs(enabled=True, chunk_chars=30_000, overlap_ratio=0.15)
    controller = PipelineController(app_model, tracks, meta, preferences=prefs)

    merged = tmp_path / "merged.txt"
    merged.write_text("hello", encoding="utf-8")
    controller._maybe_chunk_output(str(merged))

    assert len(calls) == 1
    assert calls[0]["chunk_chars"] == 30_000
    assert calls[0]["overlap_ratio"] == 0.15
    assert controller.chunksDir.endswith("chunks")


def test_maybe_chunk_output_skips_when_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    _ensure_app()

    calls: list = []
    monkeypatch.setattr(
        "ui.engines.pipeline_controller.chunk_text_file",
        lambda *a, **kw: calls.append((a, kw)),
    )

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    prefs = _StubChunkingPrefs(enabled=False)
    controller = PipelineController(app_model, tracks, meta, preferences=prefs)

    controller._maybe_chunk_output(str(tmp_path / "merged.txt"))

    assert calls == []
    assert controller.chunksDir == ""


def test_maybe_chunk_output_swallows_chunker_failures(
    tmp_path: Path, monkeypatch
) -> None:
    _ensure_app()

    def _boom(*a, **kw):
        raise ValueError("merged file is empty")

    monkeypatch.setattr(
        "ui.engines.pipeline_controller.chunk_text_file", _boom
    )

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    prefs = _StubChunkingPrefs(enabled=True)
    controller = PipelineController(app_model, tracks, meta, preferences=prefs)

    # Must not raise — chunker failure is non-fatal (merged.txt is done).
    controller._maybe_chunk_output(str(tmp_path / "merged.txt"))
    assert controller.chunksDir == ""
