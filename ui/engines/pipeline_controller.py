"""Orchestrates phase transitions and threaded workers.

Sits between :class:`AppModel` (phase state) and
:class:`TrackListModel` (per-track progress). QML calls
:py:meth:`runAsr` to start processing and :py:meth:`cancel` to abort.

This slice runs **one** track (row 0) through the simulated
:class:`AsrWorker`. Parallel / sequential multi-track orchestration
arrives in step 6.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ui.engines.asr_worker import AsrWorker
from ui.models.app_model import AppModel
from ui.models.session_mock import TrackListModel


class PipelineController(QObject):
    """Kicks off and tears down ASR workers.

    Holds strong references to both the thread and the worker so
    neither gets collected while running — QThread detaches its
    worker's parent and will silently stop sending signals if the
    worker is GC'd mid-run.
    """

    #: Emitted when the controller finishes (or is cancelled). QML can
    #: listen for this to flip UI affordances back to idle.
    finished = Signal()

    def __init__(
        self,
        app_model: AppModel,
        tracks: TrackListModel,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._app = app_model
        self._tracks = tracks
        self._thread: QThread | None = None
        self._worker: AsrWorker | None = None

    # ── QML API ───────────────────────────────────────────────────────
    @Slot()
    def runAsr(self) -> None:
        """Start transcribing the first non-excluded track.

        If a worker is already running, this is a no-op — the Run
        button flips to Pause/Cancel while a job is active, so a
        second ``runAsr`` should not land here in practice, but we
        guard anyway.
        """

        if self._thread is not None and self._thread.isRunning():
            return

        row = self._first_active_row()
        if row is None:
            return

        self._tracks.resetProgress()
        self._app.phase = "asr"
        self._spawn(row)

    @Slot()
    def cancel(self) -> None:
        """Abort the current worker and return to the idle phase."""

        if self._worker is not None:
            self._worker.cancel()
        # Phase flip happens in _onFinished once the thread really
        # quits — otherwise QML would see a brief idle state while
        # the worker was still winding down on its own thread.

    # ── Internals ─────────────────────────────────────────────────────
    def _first_active_row(self) -> int | None:
        for row in range(self._tracks.rowCount()):
            idx = self._tracks.index(row, 0)
            if not self._tracks.data(idx, TrackListModel.ExcludedRole):
                return row
        return None

    def _spawn(self, row: int) -> None:
        thread = QThread(self)
        worker = AsrWorker(row)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        # Queued by default since worker lives on `thread`.
        worker.progress.connect(self._onProgress)
        worker.done.connect(self._onDone)
        worker.error.connect(self._onError)

        # `finished` is emitted at the tail of `AsrWorker.run` for
        # every exit path (natural, cancelled, errored). Route it
        # through thread.quit so cancellation cleanly stops the event
        # loop too.
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._onFinished)

        self._thread = thread
        self._worker = worker
        thread.start()

    # ── Signal handlers (main thread) ─────────────────────────────────
    @Slot(int, float)
    def _onProgress(self, row: int, pct: float) -> None:
        self._tracks.setProgress(row, pct)

    @Slot(int)
    def _onDone(self, row: int) -> None:
        # For this slice we stop at "done" once ASR finishes — the
        # merger wiring in step 7 will instead flip phase to "merge"
        # here and then to "done" when the MergerWorker finishes.
        self._app.phase = "done"

    @Slot(int, str)
    def _onError(self, row: int, message: str) -> None:
        # Surfacing proper error UI (toast / inline chip) lands with
        # the full error-state step; for now just flip to failed so
        # the stepper can reflect it.
        self._app.phase = "failed"

    @Slot()
    def _onFinished(self) -> None:
        """Clean up the thread/worker pair and drop references."""

        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

        # If the user cancelled without a successful done / error,
        # leave phase at idle so the action button returns to Run.
        if self._app.phase == "asr":
            self._app.phase = "idle"
            self._tracks.resetProgress()

        self.finished.emit()
