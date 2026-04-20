"""Single-track ASR worker — invokes ``core.asr.transcribe_one_track``.

Phase 6 wiring: replaces the Phase 5 time.sleep simulator with a
real call into the decomposed ASR entry point. Given a pre-built
speech :class:`sources.base.Source` (shared across the batch so
weights load once) plus an audio path, this worker:

* runs :func:`core.asr.transcribe_one_track` on the path;
* emits ``progress(row, pct)`` periodically (callback fires from
  inside the ASR loop — queued back to the UI thread);
* emits ``done(row)`` on success, ``error(row, msg)`` on failure;
* always emits ``finished()`` at the end so the owning QThread can
  quit cleanly regardless of which branch ran.

Cancellation flows through two paths that both land on the same
check inside the source's loop:

* ``QThread.requestInterruption()`` — the Qt-idiomatic cross-thread
  flag the :class:`PipelineController` sets when the user hits Cancel;
* :meth:`cancel` — a belt-and-braces internal flag for the rare case
  where the worker's thread isn't the current one (e.g. unit tests
  that don't spin up a real QThread).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.asr import transcribe_one_track
from sources.base import Source


class AsrWorker(QObject):
    """Runs ASR on one track, reports progress / completion / errors."""

    #: Emitted periodically during ASR. ``pct`` is 0..1 fraction of the
    #: track that has been processed. Routes to ``TrackListModel
    #: .setProgress`` through the default queued connection.
    progress = Signal(int, float)

    #: Emitted once when the track finishes cleanly.
    done = Signal(int)

    #: Emitted once when the ASR backend raises; ``message`` is the
    #: exception's ``str()``.
    error = Signal(int, str)

    #: Always emitted exactly once in the ``finally`` block, after the
    #: per-outcome signal. ``PipelineController`` wires it to the
    #: owning QThread's ``quit`` so every branch tears down the thread.
    finished = Signal()

    def __init__(self, row: int, source: Source, audio_path: Path) -> None:
        super().__init__()
        self._row = row
        self._source = source
        self._audio_path = audio_path
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        """Transcribe ``_audio_path`` via ``_source``, emit signals.

        ``on_progress`` / ``should_cancel`` are closures so Qt doesn't
        marshal them — they run inside the source's tight loop. Only
        the signal ``emit`` at the end is thread-boundary-crossing.
        """

        def _on_progress(pct: float) -> None:
            self.progress.emit(self._row, pct)

        def _should_cancel() -> bool:
            if self._cancelled:
                return True
            thread = QThread.currentThread()
            # When the worker is moved onto a QThread, currentThread()
            # returns that worker thread; isInterruptionRequested is
            # the Qt-safe cross-thread cancel flag.
            if thread is not None and thread.isInterruptionRequested():
                return True
            return False

        try:
            transcribe_one_track(
                self._source,
                self._audio_path,
                on_progress=_on_progress,
                should_cancel=_should_cancel,
            )
            # If cancellation landed mid-file the source returned
            # partial segments and didn't raise — don't signal "done"
            # in that case, the PipelineController's own ``_cancelled``
            # flag decides whether to advance or bail.
            if not _should_cancel():
                self.done.emit(self._row)
        except Exception as exc:  # noqa: BLE001 — surface any failure
            self.error.emit(self._row, str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self) -> None:
        """Request early termination from any thread.

        Reads and writes on a single bool attribute are atomic enough
        for this single-flag use; cross-thread visibility is carried
        by the GIL / signal slot machinery.
        """

        self._cancelled = True
