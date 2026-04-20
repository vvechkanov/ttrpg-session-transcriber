"""Orchestrates phase transitions and threaded ASR workers.

Sits between :class:`AppModel` (phase state) and
:class:`TrackListModel` (per-track progress / state). QML calls
:py:meth:`runAsr` to start processing and :py:meth:`cancel` to abort.

Step 6 runs **all non-excluded tracks sequentially** — one
:class:`AsrWorker` at a time, reusing the same thread slot. Sequential
is the right default per the handoff's threading note: each worker
loads its own model unless shared carefully, and for local use the
RAM cost of parallel usually outweighs the wall-clock saving.

Any row marked *cached* is skipped with its progress snapped to 1.0.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ui.engines.asr_worker import AsrWorker
from ui.models.app_model import AppModel
from ui.models.session_mock import TrackListModel


# Mock cache policy: pretend row 1 (Boris) already has a transcript on
# disk, so the pipeline skips it with the "cached" status chip. Real
# cache lookup is a core/cache.py concern that arrives later.
_CACHED_ROWS: frozenset[int] = frozenset({1})


class PipelineController(QObject):
    """Kicks off and tears down ASR workers, one row at a time.

    Holds strong references to both the thread and the worker so
    neither gets collected while running — QThread detaches its
    worker's parent and will silently stop sending signals if the
    worker is GC'd mid-run.
    """

    #: Emitted when the controller finishes the whole queue (or was
    #: cancelled). QML can hook this to flip UI affordances.
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

        self._queue: list[int] = []
        self._cancelled: bool = False

    # ── QML API ───────────────────────────────────────────────────────
    @Slot()
    def runAsr(self) -> None:
        """Reset state and process all non-excluded tracks in order.

        If a worker is already running, this is a no-op — the Run
        button flips to Cancel while a job is active.
        """

        if self._thread is not None and self._thread.isRunning():
            return

        self._tracks.resetProgress()
        self._tracks.resetStates()
        self._cancelled = False

        # Initial marking: every non-excluded row goes into the queue
        # as "queued", cached rows are removed from the queue and get
        # their progress snapped to 1.0 so the waveform reads "done".
        self._queue = []
        for row in range(self._tracks.rowCount()):
            if self._is_excluded(row):
                continue
            if row in _CACHED_ROWS:
                self._tracks.setState(row, "cached")
                self._tracks.setProgress(row, 1.0)
            else:
                self._tracks.setState(row, "queued")
                self._queue.append(row)

        if not self._queue:
            # All eligible tracks were cached — jump straight to done.
            self._app.phase = "done"
            self.finished.emit()
            return

        self._app.phase = "asr"
        self._advance()

    @Slot()
    def cancel(self) -> None:
        """Abort the current worker and drain the queue.

        We flag the controller first so the pipeline-level ``cancel``
        is decisive: even if the in-flight worker's ``run`` happens to
        emit a final ``done`` before the cancel flag is seen, we still
        skip spawning the next row.
        """

        self._cancelled = True
        if self._worker is not None:
            self._worker.cancel()

    # ── Internals ─────────────────────────────────────────────────────
    def _is_excluded(self, row: int) -> bool:
        idx = self._tracks.index(row, 0)
        return bool(self._tracks.data(idx, TrackListModel.ExcludedRole))

    def _advance(self) -> None:
        """Spawn a worker for the head of the queue, or finish."""

        if self._cancelled or not self._queue:
            self._finish_pipeline()
            return

        row = self._queue.pop(0)
        self._tracks.setState(row, "running")
        self._spawn(row)

    def _spawn(self, row: int) -> None:
        thread = QThread(self)
        worker = AsrWorker(row)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.progress.connect(self._onProgress)
        worker.done.connect(self._onDone)
        worker.error.connect(self._onError)

        worker.finished.connect(thread.quit)
        thread.finished.connect(self._onThreadFinished)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _finish_pipeline(self) -> None:
        """Close out the pipeline after the queue drains or is aborted."""

        if self._cancelled:
            # Leave any completed rows' "done" / "cached" status; clear
            # only the queued / in-flight ones so the UI reads clean.
            for row in range(self._tracks.rowCount()):
                idx = self._tracks.index(row, 0)
                state = self._tracks.data(idx, TrackListModel.StateRole)
                if state in ("queued", "running"):
                    self._tracks.setState(row, "idle")
                    self._tracks.setProgress(row, 0.0)
            self._app.phase = "idle"
        else:
            self._app.phase = "done"
        self.finished.emit()

    # ── Signal handlers (main thread) ─────────────────────────────────
    @Slot(int, float)
    def _onProgress(self, row: int, pct: float) -> None:
        self._tracks.setProgress(row, pct)

    @Slot(int)
    def _onDone(self, row: int) -> None:
        self._tracks.setProgress(row, 1.0)
        self._tracks.setState(row, "done")

    @Slot(int, str)
    def _onError(self, row: int, message: str) -> None:
        self._tracks.setError(row, message)

    @Slot()
    def _onThreadFinished(self) -> None:
        """Clean up the thread/worker pair and advance the queue."""

        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

        self._advance()
