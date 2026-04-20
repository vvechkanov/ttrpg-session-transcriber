"""Orchestrates phase transitions and threaded ASR workers.

Sits between :class:`AppModel` (phase state) and
:class:`TrackListModel` (per-track progress / state). QML calls
:py:meth:`runAsr` to start processing and :py:meth:`cancel` to abort.

Runs **all non-excluded tracks sequentially**, one
:class:`AsrWorker` at a time on a fresh :class:`QThread`. Sequential
is the right default per the handoff threading note: each backend
loads its own model unless shared carefully, and for local use the
RAM cost of parallelism usually outweighs the wall-clock saving.

Source instances are cached by ``model_id`` across the batch so a
3 GB faster-whisper weights file loads once even if every track
picks the same override. Rows that declare an unknown ``model_id``
or are missing an ``audio_path`` (common when the user has not yet
dropped a folder) fail fast with a user-visible error.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, QThread, Signal, Slot

from core.asr import AsrSource, make_source
from core.discovery import find_fvtt_chat_log
from domain.annotations import SpeechSegment
from ui.engines.asr_worker import AsrWorker
from ui.engines.merger_worker import MergerWorker
from ui.models.app_model import AppModel
from ui.models.session import SessionMeta, TrackListModel

if TYPE_CHECKING:
    # ModelRegistry imports InstallWorker, which imports this module
    # through ``ui.engines.__init__``. Keep the type-only import here
    # so the runtime load order stays linear.
    from ui.models.app_preferences import AppPreferences
    from ui.models.model_registry import ModelRegistry


def _format_bytes(size: int) -> str:
    """Short human-readable size — "12 KB", "1.3 MB", "—" on zero."""

    if size <= 0:
        return "—"
    if size < 1024:
        return f"{size} B"
    kb = size / 1024
    if kb < 1024:
        return f"{int(round(kb))} KB"
    mb = size / (1024 * 1024)
    return f"{mb:.1f} MB"


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

    outputPathChanged = Signal()

    @Property(str, notify=outputPathChanged)
    def outputPath(self) -> str:
        return self._output_path

    def __init__(
        self,
        app_model: AppModel,
        tracks: TrackListModel,
        session_meta: SessionMeta | None = None,
        model_registry: "ModelRegistry | None" = None,
        preferences: "AppPreferences | None" = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._app = app_model
        self._tracks = tracks
        self._session = session_meta
        #: Optional link to :class:`ui.models.model_registry.ModelRegistry`.
        #: Tracks with an empty ``model_id`` delegate to the registry's
        #: active backend. Optional so unit tests can construct the
        #: controller with just a :class:`TrackListModel`.
        self._registry = model_registry
        #: Optional link to :class:`ui.models.app_preferences.AppPreferences`.
        #: When present, :meth:`_get_or_make_source` snapshots the global
        #: ASR options into every freshly-created backend.
        self._preferences = preferences

        # Active ASR worker (Phase 6).
        self._thread: QThread | None = None
        self._worker: AsrWorker | None = None

        # Active merger worker (Phase 7). Kept as a separate pair — the
        # merge pass starts *after* the ASR queue drains and plays a
        # completely different role in the pipeline.
        self._merge_thread: QThread | None = None
        self._merge_worker: MergerWorker | None = None

        self._queue: list[int] = []
        self._cancelled: bool = False

        #: ASR source cache: one Source per ``model_id`` across the
        #: batch. Loading a faster-whisper weights file costs several
        #: hundred milliseconds; the cache amortises that to once per
        #: model even if every track picks the same override.
        self._sources: dict[str, AsrSource] = {}

        #: Accumulates per-row segment lists as each AsrWorker completes.
        #: Flattened when the merge pass spawns.
        self._collected_segments: dict[int, list[SpeechSegment]] = {}

        #: Filesystem path reported by the merger on success. QML reads
        #: it through :pyattr:`outputPath` once the done phase is up.
        self._output_path: str = ""

    # ── QML API ───────────────────────────────────────────────────────
    @Slot()
    def runAsr(self) -> None:
        """Reset state and process all non-excluded tracks in order.

        If a worker is already running, this is a no-op — the Run
        button flips to Cancel while a job is active.
        """

        if self._thread is not None and self._thread.isRunning():
            return
        if self._merge_thread is not None and self._merge_thread.isRunning():
            return

        self._tracks.resetProgress()
        self._tracks.resetStates()
        self._app.clearMergeState()
        self._app.setErrorMessage("")
        if self._output_path:
            self._output_path = ""
            self.outputPathChanged.emit()
        self._cancelled = False
        self._collected_segments = {}

        # Initial marking: every non-excluded row is queued. On-disk
        # cache lookup (skipping rows that already have a transcript)
        # is a core/cache.py concern and is not wired yet — until it
        # lands the pipeline re-runs ASR on every non-excluded row.
        self._queue = []
        for row in range(self._tracks.rowCount()):
            if self._is_excluded(row):
                continue
            self._tracks.setState(row, "queued")
            self._queue.append(row)

        if not self._queue:
            # No eligible tracks — skip ASR and go straight to merge.
            self._app.phase = "merge"
            self._spawn_merger()
            return

        self._app.phase = "asr"
        self._advance()

    @Slot()
    def cancel(self) -> None:
        """Abort the current worker and drain the queue.

        We flag the controller first so the pipeline-level ``cancel``
        is decisive: even if the in-flight worker's ``run`` happens to
        emit a final ``done`` before the cancel flag is seen, we still
        skip spawning the next row. Both channels converge inside the
        source's ASR loop — ``requestInterruption`` is the idiomatic
        Qt cross-thread flag, ``worker.cancel`` a defensive fallback.
        """

        self._cancelled = True
        if self._thread is not None:
            self._thread.requestInterruption()
        if self._worker is not None:
            self._worker.cancel()
        if self._merge_worker is not None:
            self._merge_worker.cancel()

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

        # Resolve the backend + audio path for this row BEFORE flipping
        # its state to "running". Missing audio or an unknown model_id
        # are user-visible errors, not crashes.
        audio_path_str = self._tracks.audioPathFor(row)
        if not audio_path_str:
            self._tracks.setError(
                row,
                "Нет аудиофайла — перетащите папку сессии перед запуском",
            )
            self._advance()
            return

        model_id = self._tracks.modelIdFor(row) or self._active_model_id()
        try:
            source = self._get_or_make_source(model_id)
        except (ValueError, RuntimeError) as exc:
            self._tracks.setError(row, str(exc))
            self._advance()
            return

        self._tracks.setState(row, "running")
        self._spawn(row, source, Path(audio_path_str))

    def _active_model_id(self) -> str:
        """Resolve the fallback ASR model id for rows without an override.

        Returns the registry's active backend when one was wired into
        the controller, otherwise falls back to ``"gigaam"`` so tests
        and older callers keep working.
        """

        if self._registry is not None:
            return self._registry.activeModelId or "gigaam"
        return "gigaam"

    def _get_or_make_source(self, model_id: str) -> AsrSource:
        """Return the cached Source for ``model_id``, creating it on miss.

        Caching across the batch ensures each weights file loads once
        per session even if every track picks the same override.
        ``make_source`` raises ``ValueError`` on unknown IDs and
        ``RuntimeError`` if the backend isn't installed — both are
        converted to per-track errors upstream.
        """

        if model_id not in self._sources:
            options = (
                self._preferences.build_asr_options()
                if self._preferences is not None
                else None
            )
            self._sources[model_id] = make_source(model_id, options=options)
        return self._sources[model_id]

    def _spawn(self, row: int, source: AsrSource, audio_path: Path) -> None:
        thread = QThread(self)
        worker = AsrWorker(row, source, audio_path)
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
        """Close out the ASR queue — either advance to merge, or abort."""

        if self._cancelled:
            # Leave any completed rows' "done" / "cached" status; clear
            # only the queued / in-flight ones so the UI reads clean.
            for row in range(self._tracks.rowCount()):
                idx = self._tracks.index(row, 0)
                state = self._tracks.data(idx, TrackListModel.StateRole)
                if state in ("queued", "running"):
                    self._tracks.setState(row, "idle")
                    self._tracks.setProgress(row, 0.0)
            self._app.clearMergeState()
            self._app.phase = "idle"
            self._sources.clear()
            self.finished.emit()
            return

        # ASR queue drained cleanly — start the merge pass. Even if
        # every row failed, we still kick merger off (it will write an
        # empty transcript) so the UI has a definitive done state.
        self._app.phase = "merge"
        self._spawn_merger()

    # ── Merger orchestration ──────────────────────────────────────────
    def _spawn_merger(self) -> None:
        # Flatten per-row segments into one list for the merger input.
        # Rows that didn't produce segments (cached, failed, excluded)
        # silently contribute nothing — merger handles an empty speech
        # list fine.
        all_segments: list[SpeechSegment] = []
        for row in sorted(self._collected_segments.keys()):
            all_segments.extend(self._collected_segments[row])

        session_dir_str = self._session.sessionDir() if self._session is not None else ""
        if not session_dir_str:
            # No real session open — nothing to write merged.txt to.
            # Surface as an error phase so the UI stops on "failed"
            # rather than spinning.
            self._app.setErrorMessage(
                "Сессия не выбрана — откройте папку перед запуском."
            )
            self._app.phase = "failed"
            self._sources.clear()
            self.finished.emit()
            return

        session_dir = Path(session_dir_str)
        chat_log = find_fvtt_chat_log(session_dir)
        total_seconds = float(self._session.totalSeconds) if self._session is not None else 0.0

        thread = QThread(self)
        worker = MergerWorker(
            session_dir=session_dir,
            speech_segments=all_segments,
            chat_log_path=chat_log,
            total_duration=total_seconds,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.progress.connect(self._onMergeProgress)
        worker.gapFilled.connect(self._onGapFilled)
        worker.done.connect(self._onMergeDone)
        worker.error.connect(self._onMergeError)

        worker.finished.connect(thread.quit)
        thread.finished.connect(self._onMergeThreadFinished)

        self._merge_thread = thread
        self._merge_worker = worker
        thread.start()

    @Slot(float)
    def _onMergeProgress(self, pct: float) -> None:
        self._app.mergeProgress = pct

    @Slot(float, str)
    def _onGapFilled(self, position_pct: float, source_id: str) -> None:
        self._app.addStitch(position_pct)

    @Slot(str)
    def _onMergeDone(self, path: str) -> None:
        self._output_path = path
        self.outputPathChanged.emit()
        self._app.setDoneSummary(self._compute_done_summary(path))
        self._app.phase = "done"

    def _compute_done_summary(self, output_path: str) -> dict[str, str | int]:
        """Build the done-phase summary dict from real artefacts.

        Reads merged.txt once for byte size + word count; derives cue
        count from the accumulated per-track segments (one cue per
        segment is a decent approximation — gluing happens inside the
        merger and doesn't split 1:1). Session length comes from
        :class:`SessionMeta`.
        """

        try:
            file_bytes = Path(output_path).stat().st_size
            text = Path(output_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            file_bytes = 0
            text = ""

        word_count = sum(1 for w in text.split() if w)
        cue_count = sum(len(segs) for segs in self._collected_segments.values())
        track_count = sum(
            1
            for row in range(self._tracks.rowCount())
            if not self._is_excluded(row)
        )

        total_min = int(self._session.totalMinutes) if self._session is not None else 0
        hours, minutes = divmod(total_min, 60)
        session_length = f"{hours} ч {minutes:02d} м" if hours else f"{minutes} м"

        return {
            "durationLabel": f"Готово · {track_count} дорожек",
            "statsLine": f"{track_count} дорожек · {cue_count} реплик · {word_count} слов",
            "fileSize": _format_bytes(file_bytes),
            "wordCount": f"{word_count} слов",
            "cueCount": f"{cue_count} реплик",
            "sessionLength": session_length,
        }

    @Slot(str)
    def _onMergeError(self, message: str) -> None:
        # The merger either raised or reported a failure string. Stash
        # the message on AppModel so QML's FailedBanner can render it
        # and flip the phase — the banner is keyed on ``phase=failed``.
        self._app.setErrorMessage(
            message or "Сборка merged.txt не удалась."
        )
        self._app.phase = "failed"

    @Slot()
    def _onMergeThreadFinished(self) -> None:
        if self._merge_worker is not None:
            self._merge_worker.deleteLater()
            self._merge_worker = None
        if self._merge_thread is not None:
            self._merge_thread.deleteLater()
            self._merge_thread = None

        # If the user cancelled mid-merge we still need to return to
        # idle — the natural done/error paths already moved phase.
        if self._cancelled and self._app.phase == "merge":
            self._app.clearMergeState()
            self._app.phase = "idle"

        self.finished.emit()

    # ── Signal handlers (main thread) ─────────────────────────────────
    @Slot(int, float)
    def _onProgress(self, row: int, pct: float) -> None:
        self._tracks.setProgress(row, pct)

    @Slot(int, list)
    def _onDone(self, row: int, segments: list) -> None:
        self._collected_segments[row] = list(segments)
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
