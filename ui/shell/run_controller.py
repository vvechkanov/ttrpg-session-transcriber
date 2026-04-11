"""Background runner for ``core.pipeline.run`` (ADR-017 Phase 6).

``core.pipeline.run`` is synchronous and CPU/GPU-bound. Running it on
the GUI thread would freeze the Qt event loop. :class:`RunController`
wraps it in a ``QThread`` subclass and publishes four Qt signals:

    * ``started()``              — pipeline entered ``start`` stage;
    * ``stage(name, message)``   — stage tick (``speech`` / ``chat`` /
                                    ``merge`` / ``render`` / ``done``);
    * ``finished(output_path)``  — pipeline returned cleanly;
    * ``failed(error_text)``     — pipeline raised an exception.

The controller owns a single thread at a time. ``start(...)`` is a
no-op while ``is_running`` is True — callers must wait for
``finished`` / ``failed`` before launching a new run. ``cancel()``
does a best-effort ``QThread.requestInterruption`` — the pipeline
itself does NOT check for interruption flags today, so cancel only
wins at stage boundaries (stretch goal for Phase 7+).

Design note (Phase 10 final test hardening):

    The original implementation used the canonical Qt pattern of a
    ``QObject`` worker moved into a ``QThread`` via
    ``moveToThread`` + auto-connected queued signals. On PySide6
    6.11 + Windows this pattern segfaulted at worker teardown when
    the parent controller was garbage-collected between the worker's
    ``finished`` emission and the main-thread slot dispatch. The
    workaround is to subclass ``QThread`` directly — no separate
    ``QObject`` worker, no ``moveToThread`` — and emit signals from
    the thread's own ``run`` method. Qt's automatic-connection type
    still picks ``QueuedConnection`` for cross-thread receivers, so
    slot bodies fire on the main thread as before.
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


class _PipelineThread(QThread):
    """Dedicated ``QThread`` that runs one pipeline job.

    Kept private — :class:`RunController` is the only caller.
    All signals emitted from ``run`` cross thread boundaries to the
    controller's slots via automatic queued connections.
    """

    started_signal = Signal()
    stage = Signal(str, str)
    finished_signal = Signal(str)
    failed = Signal(str)

    def __init__(self, request: RunRequest, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._request = request

    def run(self) -> None:  # noqa: D401 — Qt override
        """Execute the pipeline; emit progress through signals."""

        def _stage_cb(stage: PipelineStage, message: str) -> None:
            # Qt auto-converts Literal to str on signal edge
            self.stage.emit(stage, message)

        try:
            self.started_signal.emit()
            pipeline_run(
                self._request.session_dir,
                self._request.params,
                on_stage=_stage_cb,
            )
            output_path = (
                self._request.session_dir / self._request.params.output_filename
            )
            self.finished_signal.emit(str(output_path))
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
        self._thread: _PipelineThread | None = None

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

        thread = _PipelineThread(request, parent=self)

        # Forward thread-side signals to the controller's public signals
        # via explicit slot methods rather than ``.emit`` bound references
        # (PySide6 6.11 regression — segfaults when cross-thread queued
        # connections target a C++ method pointer whose owning QObject
        # is finalising on the main thread).
        thread.started_signal.connect(self._forward_started)
        thread.stage.connect(self._forward_stage)
        thread.finished_signal.connect(self._forward_finished)
        thread.failed.connect(self._forward_failed)

        # Teardown hook — Qt's QThread.finished fires once run() returns.
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
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

    # ── Signal forwarding slots ──────────────────────────────────────

    def _forward_started(self) -> None:
        self.started.emit()

    def _forward_stage(self, name: str, message: str) -> None:
        self.stage.emit(name, message)

    def _forward_finished(self, output_path: str) -> None:
        self.finished.emit(output_path)

    def _forward_failed(self, error_text: str) -> None:
        self.failed.emit(error_text)

    def _on_thread_finished(self) -> None:
        """Release the thread once it has cleanly exited ``run``."""
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.deleteLater()
