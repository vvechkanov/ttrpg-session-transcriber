"""Phase 6 — tests for ``core.pipeline.run`` stage callback hook.

Verifies that ``run(on_stage=...)`` invokes the callback in the right
order (start → speech → chat → merge → render → done) and that the
default / absent callback path still works (byte-compat with earlier
tests and CLI callers).

We mock out ``SPEECH_SOURCES`` / ``find_fvtt_chat_log`` / ``MERGERS``
/ ``RENDERERS`` / ``check_gpu_or_warn`` so the test never touches
real ASR backends or GPU detection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.pipeline import PipelineParams, run
from sources.base import Source


class _FakeSource(Source):
    name = "fake"

    def __init__(self, **_: Any) -> None:
        pass

    def extract(self, session_dir: Path) -> list:
        return []


class _FakeMerger:
    def merge(self, timeline):
        return []


class _FakeRenderer:
    def render(self, events) -> bytes:
        return b""


@pytest.fixture
def patched_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Patch pipeline so run() executes without real ASR / chat / GPU."""
    monkeypatch.setattr(
        "core.pipeline.SPEECH_SOURCES", {"fake": _FakeSource}
    )
    monkeypatch.setattr("core.pipeline.MERGERS", {"script": _FakeMerger})
    monkeypatch.setattr("core.pipeline.RENDERERS", {"plain-text": _FakeRenderer})
    monkeypatch.setattr("core.pipeline.check_gpu_or_warn", lambda device: None)
    monkeypatch.setattr(
        "core.pipeline.find_fvtt_chat_log", lambda session_dir: None
    )
    monkeypatch.setattr("core.pipeline._speech_kwargs", lambda p, c: {})


def _make_params() -> PipelineParams:
    return PipelineParams(
        speech_backend="fake",
        merger="script",
        renderer="plain-text",
        output_filename="merged.txt",
        device="cpu",
    )


class TestStageCallback:
    def test_callback_receives_all_stages_in_order(
        self, tmp_path: Path, patched_pipeline
    ):
        stages: list[tuple[str, str]] = []

        def on_stage(stage: str, message: str) -> None:
            stages.append((stage, message))

        run(tmp_path, _make_params(), on_stage=on_stage)

        stage_names = [s for s, _ in stages]
        assert stage_names == [
            "start",
            "speech",
            "chat",
            "merge",
            "render",
            "done",
        ]

    def test_start_message_is_session_dir_name(
        self, tmp_path: Path, patched_pipeline
    ):
        seen: list[tuple[str, str]] = []
        run(tmp_path, _make_params(), on_stage=lambda s, m: seen.append((s, m)))
        start_msg = next(m for s, m in seen if s == "start")
        assert start_msg == tmp_path.name

    def test_speech_message_is_backend_name(
        self, tmp_path: Path, patched_pipeline
    ):
        seen: list[tuple[str, str]] = []
        run(tmp_path, _make_params(), on_stage=lambda s, m: seen.append((s, m)))
        speech_msg = next(m for s, m in seen if s == "speech")
        assert speech_msg == "fake"

    def test_done_message_is_output_path(
        self, tmp_path: Path, patched_pipeline
    ):
        seen: list[tuple[str, str]] = []
        run(tmp_path, _make_params(), on_stage=lambda s, m: seen.append((s, m)))
        done_msg = next(m for s, m in seen if s == "done")
        assert done_msg.endswith("merged.txt")

    def test_callback_is_optional(self, tmp_path: Path, patched_pipeline):
        """run() without on_stage kwarg should still succeed (byte-compat)."""
        # Should not raise
        run(tmp_path, _make_params())

    def test_session_dir_missing_raises_before_callback(
        self, tmp_path: Path, patched_pipeline
    ):
        """FileNotFoundError fires before any stage is emitted."""
        bogus = tmp_path / "does-not-exist"
        seen: list[str] = []
        with pytest.raises(FileNotFoundError):
            run(bogus, _make_params(), on_stage=lambda s, m: seen.append(s))
        assert seen == []


class TestChunkStage:
    """#7 7A — ``"chunk"`` stage is emitted only when chunking enabled."""

    def test_chunk_stage_skipped_when_disabled(
        self, tmp_path: Path, patched_pipeline
    ):
        stages: list[str] = []
        run(
            tmp_path,
            _make_params(),
            on_stage=lambda s, m: stages.append(s),
        )
        assert "chunk" not in stages

    def test_chunk_stage_emitted_when_enabled(
        self,
        tmp_path: Path,
        patched_pipeline,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from core.chunking import ChunkingOptions
        from core.pipeline import PipelineParams

        calls: list[dict] = []

        def _fake_chunk(merged_path, **kwargs):
            calls.append({"merged": merged_path, **kwargs})
            return tmp_path / "chunks"

        monkeypatch.setattr("core.pipeline.chunk_text_file", _fake_chunk)

        stages: list[tuple[str, str]] = []
        params = PipelineParams(
            speech_backend="fake",
            merger="script",
            renderer="plain-text",
            output_filename="merged.txt",
            device="cpu",
            chunking=ChunkingOptions(
                enabled=True, chunk_chars=30_000, overlap_ratio=0.15
            ),
        )
        run(tmp_path, params, on_stage=lambda s, m: stages.append((s, m)))

        stage_names = [s for s, _ in stages]
        assert stage_names == [
            "start",
            "speech",
            "chat",
            "merge",
            "render",
            "chunk",
            "done",
        ]
        assert len(calls) == 1
        assert calls[0]["chunk_chars"] == 30_000
        assert calls[0]["overlap_ratio"] == pytest.approx(0.15)

    def test_chunk_failure_does_not_break_pipeline(
        self,
        tmp_path: Path,
        patched_pipeline,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from core.chunking import ChunkingOptions
        from core.pipeline import PipelineParams

        def _boom(merged_path, **kwargs):
            raise ValueError("merged file is empty")

        monkeypatch.setattr("core.pipeline.chunk_text_file", _boom)

        stages: list[str] = []
        params = PipelineParams(
            speech_backend="fake",
            merger="script",
            renderer="plain-text",
            output_filename="merged.txt",
            device="cpu",
            chunking=ChunkingOptions(enabled=True),
        )
        run(tmp_path, params, on_stage=lambda s, m: stages.append(s))

        assert "done" in stages
        assert stages.index("chunk") < stages.index("done")
