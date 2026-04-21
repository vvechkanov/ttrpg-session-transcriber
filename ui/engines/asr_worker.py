"""Single-row ASR worker — invokes ``core.asr.transcribe_one_track``.

Phase 6 wiring: replaces the Phase 5 time.sleep simulator with a
real call into the decomposed ASR entry point. Given a pre-built
speech :class:`core.asr.AsrSource` (shared across the batch so
weights load once) plus an ordered list of :class:`SegmentJob` (one
per ``TrackSegment`` on the row), this worker:

* runs :func:`core.asr.transcribe_one_track` per segment, concatenating
  shifted :class:`SpeechSegment` results;
* emits ``progress(row, pct)`` periodically — weighted by segment
  duration so ``pct`` advances smoothly across a multi-Craig row;
* emits ``done(row, segments)`` on success, ``error(row, msg)`` on
  failure;
* always emits ``finished()`` at the end so the owning QThread can
  quit cleanly regardless of which branch ran.

Multi-segment (feature #4b) design: one worker owns the whole row.
Running N sub-workers would fragment the single progress stream and
complicate cancellation; a serial inner loop keeps the contract with
:class:`PipelineController` unchanged.

Cancellation flows through two paths that both land on the same
check inside the source's loop:

* ``QThread.requestInterruption()`` — the Qt-idiomatic cross-thread
  flag the :class:`PipelineController` sets when the user hits Cancel;
* :meth:`cancel` — a belt-and-braces internal flag for the rare case
  where the worker's thread isn't the current one (e.g. unit tests
  that don't spin up a real QThread).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.asr import AsrSource, transcribe_one_track
from domain.annotations import SpeechSegment


@dataclass(frozen=True)
class SegmentJob:
    """One audio segment to transcribe as part of a row's ASR pass.

    ``offset_sec`` is added to every :class:`SpeechSegment.start` /
    ``.end`` so the concatenated result lives in the session-global
    timeline (zero point = ``TimelineWindow.t0``).

    ``duration_sec`` is used to weight per-segment progress updates.
    ``0.0`` (unknown) falls back to equal weighting across all
    segments on the row.
    """

    audio_path: Path
    offset_sec: float = 0.0
    duration_sec: float = 0.0


class AsrWorker(QObject):
    """Runs ASR on one row (1+ segments), reports progress / completion / errors."""

    #: Emitted periodically during ASR. ``pct`` is 0..1 fraction of the
    #: row that has been processed. Routes to ``TrackListModel
    #: .setProgress`` through the default queued connection.
    progress = Signal(int, float)

    #: Emitted once when the row finishes cleanly. Carries
    #: ``(row, segments)`` so ``PipelineController`` can accumulate
    #: the list for the subsequent merge pass without a side channel.
    done = Signal(int, list)

    #: Emitted once when the ASR backend raises; ``message`` is the
    #: exception's ``str()``.
    error = Signal(int, str)

    #: Always emitted exactly once in the ``finally`` block, after the
    #: per-outcome signal. ``PipelineController`` wires it to the
    #: owning QThread's ``quit`` so every branch tears down the thread.
    finished = Signal()

    def __init__(
        self,
        row: int,
        source: AsrSource,
        segments: Sequence[SegmentJob] | Path,
    ) -> None:
        """Construct a worker for ``row``.

        Accepts either a ``Sequence[SegmentJob]`` (multi-segment row,
        feature #4b) or a bare :class:`Path` for single-segment legacy
        callers that pre-date the refactor. The ``Path`` form is
        wrapped into a one-element ``SegmentJob(offset=0, duration=0)``
        so all downstream logic sees a uniform list.
        """

        super().__init__()
        self._row = row
        self._source = source
        if isinstance(segments, Path):
            self._segments: tuple[SegmentJob, ...] = (SegmentJob(audio_path=segments),)
        else:
            jobs = tuple(segments)
            if not jobs:
                raise ValueError("AsrWorker requires at least one SegmentJob")
            self._segments = jobs
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        """Transcribe every segment via ``_source``, emit signals.

        ``on_progress`` / ``should_cancel`` are closures so Qt doesn't
        marshal them — they run inside the source's tight loop. Only
        the signal ``emit`` at the end is thread-boundary-crossing.
        """

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

        weights = _compute_segment_weights(self._segments)
        completed_weight = 0.0
        collected: list[SpeechSegment] = []

        try:
            for i, job in enumerate(self._segments):
                if _should_cancel():
                    break
                segment_weight = weights[i]

                def _on_progress(
                    pct: float, base: float = completed_weight, w: float = segment_weight
                ) -> None:
                    self.progress.emit(self._row, base + pct * w)

                segs = transcribe_one_track(
                    self._source,
                    job.audio_path,
                    on_progress=_on_progress,
                    should_cancel=_should_cancel,
                    time_offset_sec=job.offset_sec,
                )
                collected.extend(segs)
                completed_weight += segment_weight

            # If cancellation landed mid-row the source returned partial
            # segments and didn't raise — don't signal "done" in that
            # case; the PipelineController's own ``_cancelled`` flag
            # decides whether to advance or bail.
            if not _should_cancel():
                self.done.emit(self._row, collected)
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


def _compute_segment_weights(segments: Sequence[SegmentJob]) -> list[float]:
    """Return per-segment weights summing to ``1.0``.

    Uses real durations when all are positive; otherwise falls back
    to equal weighting so zero-duration unknowns still produce a
    monotonically increasing progress reading.
    """

    total = sum(max(s.duration_sec, 0.0) for s in segments)
    if total <= 0.0:
        equal = 1.0 / len(segments)
        return [equal] * len(segments)
    return [s.duration_sec / total for s in segments]
