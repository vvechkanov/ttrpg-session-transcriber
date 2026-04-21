"""Background worker: compute waveform peaks for a batch of segments.

Runs on its own :class:`QThread`, calling
:func:`core.peaks.get_or_compute_peaks` once per segment and emitting
``peaksReady(row, seg_idx, peaks)`` after each file so the UI can
progressively fill lanes without waiting for the whole batch.

Feature #4 iteration 4b: the batch is a flat ``[(row, seg_idx, path),
...]`` list — one entry per :class:`ui.models.session.TrackSegment`.
Multi-Craig rows fan out naturally, and the row-level waveform mirror
happens inside :meth:`TrackListModel.setPeaks` (primary segment copied
into the row-level ``peaks`` field for legacy readers).

Also emits ``durationReady(seconds)`` after a per-segment probe so
``SessionMeta`` can grow its ruler to the longest file — that probe
runs on the worker thread instead of blocking the UI (which is what
froze the shell on folder-pick before Phase 11 polish).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, Signal, Slot

from core.peaks import get_or_compute_peaks, probe_duration


class PeaksWorker(QObject):
    """One-shot worker over a pre-ordered list of ``(row, seg_idx, path)``."""

    #: Emitted once per segment with a list of 0..1 peak values. The UI
    #: slot copies the list into ``TrackListModel``'s storage.
    peaksReady = Signal(int, int, list)

    #: Emitted once per segment with the decoded duration in seconds.
    #: ``SessionMeta.setTotalSeconds`` grows the ruler to fit the
    #: longest segment (the signal only passes the scalar — the
    #: consumer picks the max). Running the probe here keeps the UI
    #: thread responsive.
    durationReady = Signal(float)

    #: Emitted when the whole batch is done (success or skip). QML
    #: can hide loading shimmer on this.
    allDone = Signal()

    def __init__(
        self, segments: Sequence[tuple[int, int, str]]
    ) -> None:
        super().__init__()
        # Copy so in-place mutation from the caller can't surprise us
        # mid-run — the worker carries its own immutable work queue.
        self._segments = list(segments)
        self._cancelled = False

    @Slot()
    def cancel(self) -> None:
        """Stop processing after the current file completes."""

        self._cancelled = True

    @Slot()
    def run(self) -> None:
        for row, seg_idx, path_str in self._segments:
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
                self.peaksReady.emit(row, seg_idx, peaks)
        self.allDone.emit()
