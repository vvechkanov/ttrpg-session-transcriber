"""Simulated merger worker — stitches transcripts + chat logs.

Runs on its own QThread, emits progress ticks and `gapFilled`
notifications as the merger bridges Craig gaps with chat-log events.
For step 7 the "work" is just a timed loop; step 8+ swaps it for a
real ``core.merger.run`` call. The public signal shape (``progress`` /
``gapFilled`` / ``done`` / ``error`` / ``finished``) is what QML binds
to, so the backing work can change without touching the UI.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal, Slot


class MergerWorker(QObject):
    # 0..1 overall merge progress
    progress = Signal(float)
    # One vertical stitch has landed on the timeline — (pct, source_id).
    # `pct` is 0..100 so QML can position the marker directly.
    gapFilled = Signal(float, str)
    # Filesystem path to the produced merged.txt.
    done = Signal(str)
    # Human-readable failure message.
    error = Signal(str)
    # Emitted in a finally so every exit path winds the thread down.
    finished = Signal()

    #: Number of progress ticks.
    TICKS: int = 40
    TICK_INTERVAL: float = 0.05

    #: Percent offsets along the timeline where stitches will land.
    #: Taken from the HTML prototype's ``MergeStitches`` component so
    #: the visual matches the handoff.
    _STITCH_POSITIONS: tuple[float, ...] = (15, 28, 42, 58, 71, 85)

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            # Fire stitches at evenly-spaced points along the progress
            # arc so the overlay fills in as the merge advances.
            stitch_ticks = [
                int(self.TICKS * (i + 1) / (len(self._STITCH_POSITIONS) + 1))
                for i in range(len(self._STITCH_POSITIONS))
            ]
            stitch_iter = iter(zip(stitch_ticks, self._STITCH_POSITIONS))
            next_stitch = next(stitch_iter, None)

            for tick in range(self.TICKS + 1):
                if self._cancelled:
                    return

                self.progress.emit(tick / self.TICKS)

                if next_stitch is not None and tick >= next_stitch[0]:
                    self.gapFilled.emit(next_stitch[1], "foundry-chat")
                    next_stitch = next(stitch_iter, None)

                if tick < self.TICKS:
                    time.sleep(self.TICK_INTERVAL)

            self.done.emit("~/Sessions/2025-01-14/merged.txt")
        except Exception as exc:   # defensive
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True
