"""Background worker: compute waveform peaks for a batch of tracks.

Runs on its own :class:`QThread`, calling
:func:`core.peaks.get_or_compute_peaks` once per track and emitting
``peaksReady(row, peaks)`` after each file so the UI can progressively
fill lanes without waiting for the whole batch. Orchestrated by
:class:`ui.models.TrackListModel` which owns the thread lifetime and
connects the signal to :pymeth:`TrackListModel.setPeaks`.

Also emits ``durationReady(seconds)`` after a per-track probe so
``SessionMeta`` can grow its ruler to the longest track — that probe
runs on the worker thread instead of blocking the UI (which is what
froze the shell on folder-pick before Phase 11 polish).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, Signal, Slot

from core.peaks import get_or_compute_peaks, probe_duration


class PeaksWorker(QObject):
    """One-shot worker over a pre-ordered list of ``(row, path)`` pairs."""

    #: Emitted once per track with a list of 0..1 peak values. The UI
    #: slot copies the list into ``TrackListModel``'s storage.
    peaksReady = Signal(int, list)

    #: Emitted once per track with the decoded duration in seconds.
    #: SessionMeta.setTotalSeconds grows the ruler to fit the longest
    #: track. Running the probe here keeps the UI thread responsive —
    #: an earlier version probed synchronously in openSession and
    #: hung the app when ffprobe stalled.
    durationReady = Signal(float)

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
            path = Path(path_str)

            # Metadata probe first — it's sub-second and gives the
            # ruler a target length before the (slower) full decode
            # finishes.
            duration = probe_duration(path)
            if duration > 0:
                self.durationReady.emit(duration)

            if self._cancelled:
                break
            peaks = get_or_compute_peaks(path)
            if peaks:
                self.peaksReady.emit(row, peaks)
        self.allDone.emit()
