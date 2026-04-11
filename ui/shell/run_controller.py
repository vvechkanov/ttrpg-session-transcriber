"""Background runner for ``core.pipeline.run`` (ADR-017 Phase 6).

``core.pipeline.run`` is synchronous and CPU/GPU-bound. Running it on
the GUI thread would freeze the Qt event loop. :class:`RunController`
wraps it in a ``QThread`` worker and publishes four Qt signals:

    * ``started()``              — pipeline entered ``start`` stage;
    * ``stage(name, message)``   — stage tick (``speech`` / ``chat`` /
                                    ``merge`` / ``render`` / ``done``);
    * ``finished(output_path)``  — pipeline returned cleanly;
    * ``failed(error_text)``     — pipeline raised an exception.

The controller owns a single worker at a time. ``start(...)`` is a
no-op while ``is_running`` is True — callers must wait for
``finished`` / ``failed`` before launching a new run. ``cancel()``
does a best-effort ``QThread.requestInterruption`` — the pipeline
itself does NOT check for interruption flags today, so cancel only
wins at stage boundaries (stretch goal for Phase 7+).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from core.pipeline import PipelineParams, PipelineStage, run as pipeline_run

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunRequest:
    """Input payload for :meth:`RunController.start`."""

    session_dir: Path
    params: PipelineParams


class _Worker(QObject):
    """QObject living inside a ``QThread``; runs one pipeline job.

    Kept private — ``RunController`` is the only caller that spawns it.
    The worker uses queued ``Signal`` emits (auto via ``moveToThread``)
    so UI slots always fire on the main thread.
    """

    started = Signal()
    stage = Signal(str, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, request: RunRequest) -> None:
        super().__init__()
        self._request = request

    def run(self) -> None:
        """Execute the pipeline; emit progress through signals.

        Slot invoked by ``QThread.started`` — wired up in
        :meth:`RunController.start`.
        """
        def _stage_cb(stage: PipelineStage, message: str) -> None:
            # Qt auto-converts Literal to str on signal edge
            self.stage.emit(stage, message)

        try:
            self.started.emit()
            pipeline_run(
                self._request.session_dir,
                self._request.params,
                on_stage=_stage_cb,
            )
            output_path = (
                self._request.session_dir / self._request.params.output_filename
            )
            self.finished.emit(str(output_path))
        except Exception as exc:  # noqa: BLE001 — UI boundary: everything → text
            logger.exception("Pipeline run failed")
            self.failed.emit(str(exc))


class RunController(QObject):
    """Public façade for kicking off pipeline runs from the GUI.

    Usage from ``SessionScreen`` (Phase 6+)::

        ctrl = RunController(parent=self)
        ctrl.stage.connect(self._on_stage)
        ctrl.finished.connect(self._on_finished)
        ctrl.failed.connect(self._on_failed)
        ctrl.start(RunRequest(session_dir=Path(...), params=...))

    The controller takes ownership of the ``QThread``, kills it on
    cleanup, and guards against double-start.
    """

    started = Signal()
    stage = Signal(str, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _Worker | None = None

    @property
    def is_running(self) -> bool:
        """Whether a worker thread is currently executing a pipeline."""
        return self._thread is not None and self._thread.isRunning()

    def start(self, request: RunRequest) -> bool:
        """Kick off a new pipeline run in a background thread.

        Returns ``True`` if the run was accepted, ``False`` if one was
        already in progress (caller should ignore or surface a warning).
        """
        if self.is_running:
            logger.warning("RunController.start called while already running")
            return False

        thread = QThread(self)
        worker = _Worker(request)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.started.connect(self.started.emit)
        worker.stage.connect(self.stage.emit)
        worker.finished.connect(self.finished.emit)
        worker.failed.connect(self.failed.emit)

        # Teardown: both success and error paths quit the thread.
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def cancel(self) -> None:
        """Best-effort interrupt (currently a no-op inside the pipeline).

        ``core.pipeline.run`` is a tight synchronous flow without
        cancellation points, so ``cancel`` only flags the thread via
        ``requestInterruption`` — the pipeline itself doesn't check.
        Kept in the API surface so UI callers can wire the button now
        and the pipeline can opt into interruption later (Phase 7+).
        """
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()

    def _on_thread_finished(self) -> None:
        """Drop references to the worker/thread once the QThread exits."""
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
