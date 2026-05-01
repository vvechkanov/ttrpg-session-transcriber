"""Merger worker — combines per-track ASR output + chat into merged.txt.

Phase 7 wiring: replaces the Phase 5 simulated loop with a real call
into :class:`mergers.script_merger.ScriptMerger` +
:class:`renderers.plain_text.PlainTextRenderer`. The "render" phase
from ``core.pipeline.run`` is collapsed inside this worker — the
handoff's timeline exposes only ``idle/asr/merge/done``, and the
renderer call is an implementation detail of the merge step.

Signals keep the Phase 5 shape so ``PipelineController`` and
``StitchOverlay.qml`` don't have to move:

* ``progress(float)`` — 0..1 overall merge progress
* ``gapFilled(float, str)`` — ``(position_pct, source_id)`` per stitch
  point; the UI animates a vertical marker per emission
* ``done(str)`` — absolute path to the written merged.txt
* ``error(str)`` — human-readable failure
* ``finished()`` — fires once in ``finally`` so the owning thread quits
  cleanly on every exit path

Cancellation flows through :meth:`cancel` plus the worker-thread's
:meth:`QThread.isInterruptionRequested` probe; checked between chat
events and before the renderer write.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from domain.annotations import ChatMessage, GameLogEntry, SpeechSegment
from domain.timeline import Timeline
from mergers.script_merger import ScriptMerger
from renderers.plain_text import PlainTextRenderer


class MergerWorker(QObject):
    """One-shot worker that glues segments + chat into a merged.txt file."""

    #: 0..1 overall merge progress. Coarse — emissions land at the
    #: boundaries of the four logical stages (chat parse, timeline
    #: build, merge, render/write) rather than inside the tight
    #: merger loop.
    progress = Signal(float)

    #: Per stitch (``position_pct`` 0..100, ``source_id``). Fires once
    #: per chat message that lands inside the merged timeline so the
    #: StitchOverlay staggers them in.
    gapFilled = Signal(float, str)

    #: Filesystem path to the written merged.txt.
    done = Signal(str)

    #: Human-readable failure.
    error = Signal(str)

    #: Always emitted in the ``finally`` block.
    finished = Signal()

    def __init__(
        self,
        session_dir: Path,
        speech_segments: list[SpeechSegment],
        chat_log_path: Path | None = None,
        total_duration: float = 0.0,
        gap_sec: float = 1.0,
        combat_log_paths: list[Path] | None = None,
    ) -> None:
        super().__init__()
        self._session_dir = session_dir
        self._speech = list(speech_segments)
        self._chat_log_path = chat_log_path
        self._total_duration = float(total_duration)
        self._gap_sec = float(gap_sec)
        self._combat_log_paths = list(combat_log_paths or [])
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            # ── Stage 1 of 4: parse chat (if any) ──────────────────
            self.progress.emit(0.0)
            chat_messages: list[ChatMessage] = self._parse_chat()
            if self._should_cancel():
                return
            self.progress.emit(0.25)

            # ── Stage 2 of 4: fire stitch markers ──────────────────
            # Stagger them deterministically so StitchOverlay's
            # `NumberAnimation { delay: index * 60 }` has something
            # to bite on, even for short sessions with few messages.
            if chat_messages and self._total_duration > 0:
                for msg in chat_messages:
                    if self._should_cancel():
                        return
                    pct = max(0.0, min(100.0, (msg.at / self._total_duration) * 100.0))
                    self.gapFilled.emit(pct, "foundry-chat")
            self.progress.emit(0.5)

            # ── Stage 3 of 4: merge ────────────────────────────────
            game_log_entries = self._parse_combat_dumps()
            if self._should_cancel():
                return
            timeline = Timeline(
                speech=self._speech,
                emotions=[],
                chat=chat_messages,
                game_log=game_log_entries,
            )
            if self._should_cancel():
                return
            events = ScriptMerger(gap_sec=self._gap_sec).merge(timeline)
            self.progress.emit(0.8)

            # ── Stage 4 of 4: render + write ───────────────────────
            if self._should_cancel():
                return
            payload = PlainTextRenderer().render(events)

            output_path = self._session_dir / "merged.txt"
            output_path.write_bytes(payload)
            self.progress.emit(1.0)

            self.done.emit(str(output_path))

        except Exception as exc:  # noqa: BLE001 — surface any failure
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True

    # ── Internal ──────────────────────────────────────────────────
    def _should_cancel(self) -> bool:
        if self._cancelled:
            return True
        thread = QThread.currentThread()
        if thread is not None and thread.isInterruptionRequested():
            return True
        return False

    def _parse_chat(self) -> list[ChatMessage]:
        if self._chat_log_path is None:
            return []
        # Lazy import so core-less tests don't need the whole
        # sources chain — and the FvttChatSource init cost stays
        # out of the worker's hot path for sessions without chat.
        from sources.game_log.fvtt_chat import FvttChatSource

        try:
            src = FvttChatSource(chat_log_path=self._chat_log_path)
            return src.extract(self._session_dir)
        except FileNotFoundError:
            # No info.txt — chat can't be time-aligned. Surface as
            # "no chat" rather than failing the whole merge.
            return []

    def _parse_combat_dumps(self) -> list[GameLogEntry]:
        if not self._combat_log_paths:
            return []
        from sources.game_log.combat_dump import CombatDumpSource

        entries: list[GameLogEntry] = []
        for path in self._combat_log_paths:
            try:
                src = CombatDumpSource(combat_log_path=path)
                entries.extend(src.extract(self._session_dir))
            except (FileNotFoundError, ValueError, KeyError):
                # Сломанный/пустой dump не должен валить весь merge.
                continue
        return entries
