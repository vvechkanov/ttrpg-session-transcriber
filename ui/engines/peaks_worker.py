"""Background worker: compute waveform peaks for a batch of segments.

Runs on its own :class:`QThread`. Probes every segment's duration
first (metadata read, ~20 ms) so the ruler gets its full extent at
once, then decodes segments through a small thread pool, emitting
``peaksReady(row, seg_idx, peaks)`` as each finishes so lanes fill in
progressively.

Decoding used to be sequential, which left every lane blank for
several minutes on a real six-track Craig session (~16 s for the
smallest 17 MB track, minutes for a 200 MB one). ffmpeg is
single-threaded per file, so the pool converts that wait into roughly
one file's worth.

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

import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, Signal, Slot

from core.peaks import get_or_compute_peaks, probe_duration

#: How many segments to decode at once.
#:
#: Peak extraction is a full ffmpeg decode of the source file — CPU
#: bound, single-threaded per file, and slow on Craig tracks (a
#: 4h45m FLAC takes minutes). Run sequentially, a six-track session
#: left every lane blank for several minutes. Machines running this
#: have cores to spare, so decode several at once and cap the pool so
#: we never monopolise the box.
_MAX_WORKERS = max(2, min(6, (os.cpu_count() or 4) // 2))


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

    #: То же самое, но с адресом сегмента. Нужно, чтобы дорожка знала
    #: собственную длину: без неё ``TrackSegment.duration_sec``
    #: оставался ``None``, правый край сегмента считался за 100% лейна,
    #: и заливка прогресса ASR доезжала до края экрана, а не до конца
    #: звука. Скалярный ``durationReady`` остаётся — линейке нужен
    #: максимум, а не адрес.
    segmentDurationReady = Signal(int, int, float)

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
        # Durations first, for every segment, before any decode starts.
        # The probe is a metadata read (~20 ms) while a decode is
        # minutes, so this gets the ruler its full extent immediately
        # instead of growing it one slow file at a time.
        for row, seg_idx, path_str in self._segments:
            if self._cancelled:
                self.allDone.emit()
                return
            duration = probe_duration(Path(path_str))
            if duration > 0:
                self.durationReady.emit(duration)
                self.segmentDurationReady.emit(row, seg_idx, duration)

        # Then decode in parallel. Signals are emitted from this
        # thread as results land, not from the pool threads, so
        # receivers keep the same thread-affinity guarantees they had
        # when this loop was sequential.
        pending = set()
        queue = list(self._segments)
        try:
            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
                while (queue or pending) and not self._cancelled:
                    while queue and len(pending) < _MAX_WORKERS:
                        row, seg_idx, path_str = queue.pop(0)
                        future = pool.submit(get_or_compute_peaks, Path(path_str))
                        pending.add((future, row, seg_idx))

                    futures = {item[0] for item in pending}
                    done, _ = wait(futures, return_when=FIRST_COMPLETED)

                    for item in [i for i in pending if i[0] in done]:
                        pending.discard(item)
                        future, row, seg_idx = item
                        try:
                            peaks = future.result()
                        except Exception:  # noqa: BLE001 — one bad file
                            continue      # must not kill the batch
                        if peaks and not self._cancelled:
                            self.peaksReady.emit(row, seg_idx, peaks)
        finally:
            self.allDone.emit()
