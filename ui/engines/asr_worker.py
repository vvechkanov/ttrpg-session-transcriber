"""Single-track ASR worker, run on its own QThread.

For step 5 this is a **simulator** — it sleeps in small increments and
emits synthetic progress so the progress-overlay wiring can be
exercised without dragging in the real ``core/asr.py`` stack (GPU
probe, model download, faster-whisper/GigaAM imports).

Step 6 swaps the simulated loop for the real ``core.asr.transcribe_*``
call; the signal shape (``progress(int, float)`` /
``done(int)`` / ``error(int, str)``) stays the same so nothing in
QML-land has to move.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal, Slot


class AsrWorker(QObject):
    """Runs ASR for a single track, reports progress and completion.

    Lifecycle (per-worker instance):

        worker = AsrWorker(row=0)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(thread.quit)
        thread.start()

    The orchestration above lives in :class:`PipelineController`.
    """

    # row, pct(0..1)
    progress = Signal(int, float)
    # row
    done = Signal(int)
    # row, human message
    error = Signal(int, str)
    # Emitted once at the very end of ``run``, whatever branch took.
    # The orchestrator connects this to the owning QThread's ``quit``
    # slot so cancellation cleanly tears the thread down too.
    finished = Signal()

    #: Number of progress ticks per simulated transcription. Higher →
    #: smoother bar motion; lower → quicker completion during tests.
    TICKS: int = 60

    #: Seconds of sleep between ticks. ``TICKS * TICK_INTERVAL`` is the
    #: total simulated runtime — tuned to roughly 8 seconds so the
    #: wiring is observable during a manual click-through without being
    #: tedious.
    TICK_INTERVAL: float = 0.13

    def __init__(self, row: int) -> None:
        super().__init__()
        self._row = row
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        """Emit progress ticks in a simulated work loop.

        Runs on the worker thread. Progress is emitted via a direct
        Qt signal, which becomes a queued call on any main-thread
        connected slot — so the UI update happens without explicit
        ``QMetaObject.invokeMethod`` dancing.

        ``finished`` is emitted in a ``finally`` so cancellation,
        natural completion, and errors all wind the thread down the
        same way.
        """

        try:
            for tick in range(self.TICKS + 1):
                if self._cancelled:
                    return
                self.progress.emit(self._row, tick / self.TICKS)
                if tick < self.TICKS:
                    time.sleep(self.TICK_INTERVAL)
            self.done.emit(self._row)
        except Exception as exc:   # defensive — surface to UI
            self.error.emit(self._row, str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self) -> None:
        """Request early termination. Safe to call from any thread —
        ``_cancelled`` is a plain Python bool, but reads/writes on it
        are atomic enough for this single-flag use.
        """

        self._cancelled = True
