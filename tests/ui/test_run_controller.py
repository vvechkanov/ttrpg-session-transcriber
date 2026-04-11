"""Phase 6 — tests for :class:`ui.shell.run_controller.RunController`.

Verifies the QThread wrapper around ``core.pipeline.run``:
    - successful run emits ``started`` → stages → ``finished`` in
      order and delivers them on the GUI thread (pytest-qt runs a
      real event loop, so we use ``waitSignal``);
    - a second ``start(...)`` while already running is refused;
    - exceptions in the pipeline are marshalled into ``failed(str)``
      without crashing the app.

The pipeline is stubbed via ``monkeypatch`` so no ASR model is loaded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from core.pipeline import PipelineParams
from ui.shell.run_controller import RunController, RunRequest


def _fake_pipeline_success(
    session_dir: Path, params: PipelineParams, *, on_stage=None
) -> None:
    """Stand-in for ``core.pipeline.run`` that emits all six stages."""
    if on_stage is None:
        return
    on_stage("start", session_dir.name)
    on_stage("speech", params.speech_backend)
    on_stage("chat", "no chat log")
    on_stage("merge", params.merger)
    on_stage("render", params.renderer)
    (session_dir / params.output_filename).write_bytes(b"")
    on_stage("done", str(session_dir / params.output_filename))


def _fake_pipeline_failure(
    session_dir: Path, params: PipelineParams, *, on_stage=None
) -> None:
    """Stand-in that raises midway, to test ``failed`` signal."""
    if on_stage is not None:
        on_stage("start", session_dir.name)
    raise RuntimeError("boom: backend unavailable")


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    """Empty but valid session folder for the run controller."""
    return tmp_path


@pytest.fixture
def make_params():
    def _make() -> PipelineParams:
        return PipelineParams(
            speech_backend="gigaam",
            merger="script",
            renderer="plain-text",
            output_filename="merged.txt",
            device="cpu",
        )
    return _make


@pytest.mark.gui
class TestRunControllerSuccess:
    def test_success_emits_stages_then_finished(
        self,
        qtbot,
        monkeypatch: pytest.MonkeyPatch,
        session_dir: Path,
        make_params,
    ):
        monkeypatch.setattr(
            "ui.shell.run_controller.pipeline_run", _fake_pipeline_success
        )
        ctrl = RunController()
        stages: list[tuple[str, str]] = []
        ctrl.stage.connect(lambda s, m: stages.append((s, m)))

        with qtbot.waitSignal(ctrl.finished, timeout=3000) as blocker:
            assert ctrl.start(
                RunRequest(session_dir=session_dir, params=make_params())
            )

        # finished(output_path)
        assert blocker.args[0].endswith("merged.txt")
        # all six stages fired in order
        assert [s for s, _ in stages] == [
            "start",
            "speech",
            "chat",
            "merge",
            "render",
            "done",
        ]

    def test_is_running_toggles(
        self,
        qtbot,
        monkeypatch: pytest.MonkeyPatch,
        session_dir: Path,
        make_params,
    ):
        monkeypatch.setattr(
            "ui.shell.run_controller.pipeline_run", _fake_pipeline_success
        )
        ctrl = RunController()
        assert ctrl.is_running is False

        with qtbot.waitSignal(ctrl.finished, timeout=3000):
            ctrl.start(
                RunRequest(session_dir=session_dir, params=make_params())
            )

        # After the worker's thread has quit, the helper cleans up and
        # ``is_running`` must be False again.
        qtbot.waitUntil(lambda: ctrl.is_running is False, timeout=3000)


@pytest.mark.gui
class TestRunControllerFailure:
    def test_exception_routes_to_failed_signal(
        self,
        qtbot,
        monkeypatch: pytest.MonkeyPatch,
        session_dir: Path,
        make_params,
    ):
        monkeypatch.setattr(
            "ui.shell.run_controller.pipeline_run", _fake_pipeline_failure
        )
        ctrl = RunController()

        with qtbot.waitSignal(ctrl.failed, timeout=3000) as blocker:
            ctrl.start(
                RunRequest(session_dir=session_dir, params=make_params())
            )

        assert "boom" in blocker.args[0]
