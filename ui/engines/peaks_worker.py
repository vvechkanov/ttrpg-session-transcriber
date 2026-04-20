"""Background worker: compute waveform peaks for a batch of tracks.

Runs on its own :class:`QThread`, calling
:func:`core.peaks.get_or_compute_peaks` once per track and emitting
``peaksReady(row, peaks)`` after each file so the UI can progressively
fill lanes without waiting for the whole batch. Orchestrated by
:class:`ui.models.TrackListModel` which owns the thread lifetime and
connects the signal to :pymeth:`TrackListModel.setPeaks`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, Signal, Slot

from core.peaks import get_or_compute_peaks


class PeaksWorker(QObject):
    """One-shot worker over a pre-ordered list of ``(row, path)`` pairs."""

    #: Emitted once per track with a list of 0..1 peak values. The UI
    #: slot copies the list into ``TrackListModel``'s storage.
    peaksReady = Signal(int, list)

    #: Emitted when the whole batch is done (success or skip). QML
    #: can hide loading shimmer on this.
    allDone = Signal()

    def __init__(self, tracks: Sequence[tuple[int, str]]) -> None:
        super().__init__()
        # Copy so in-place mutation from the caller can't surprise us
        # mid-run — the worker carries its own immutable work queue.
        self._tracks = list(tracks)
        self._cancelled = False

    @Slot()
    def cancel(self) -> None:
        """Stop processing after the current file completes."""

        self._cancelled = True

    @Slot()
    def run(self) -> None:
        for row, path_str in self._tracks:
            if self._cancelled:
                break
            peaks = get_or_compute_peaks(Path(path_str))
            if peaks:
                self.peaksReady.emit(row, peaks)
        self.allDone.emit()
