"""Session-level view-models for the Timeline screen.

Starts empty on first launch; populated only when the user drops a
folder or picks one via the Empty-screen "Выбрать папку…" button.
:meth:`SessionMeta.openSession` discovers tracks via
:func:`core.file_matchers.detect_audio_files` and sources via
:func:`core.file_matchers.detect_fvtt_chat_logs` +
:func:`core.file_matchers.detect_combat_logs`, then emits
``sessionOpened`` so the two list models refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QUrl,
    Qt,
    Property,
    Signal,
    Slot,
)

from core.file_matchers import (
    detect_audio_files,
    detect_combat_logs,
    detect_fvtt_chat_logs,
)
from core.peaks import probe_duration




def _url_to_path(url_or_path: str) -> Path:
    """Accept either a ``file://`` URL (QML drag-and-drop) or a plain path."""

    if url_or_path.startswith("file://") or url_or_path.startswith("file:///"):
        return Path(QUrl(url_or_path).toLocalFile())
    return Path(url_or_path)


class SessionMeta(QObject):
    """Scalar session facts shared by the ruler, waveforms, and top bar.

    Exposed to QML as ``sessionMeta``. Starts with prototype defaults;
    :meth:`openSession` swaps them for real folder data and emits
    :pysig:`sessionOpened` so dependent list models (tracks, sources)
    can refresh.
    """

    sessionOpened = Signal(str)          # session dir (absolute posix-style)
    totalMinutesChanged = Signal()
    segmentSplitMinutesChanged = Signal()
    sessionTitleChanged = Signal()
    campaignTitleChanged = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._session_dir: Path | None = None
        # Empty defaults — openSession() populates real values from
        # the folder the user opens; until then the shell lands on
        # EmptyScreen (AppModel.screen defaults to "empty").
        self._total_min = 0
        self._seg_split_min = 0
        self._session_title = ""
        self._campaign_title = ""

    @Property(int, notify=totalMinutesChanged)
    def totalMinutes(self) -> int:
        return self._total_min

    @Property(int, notify=segmentSplitMinutesChanged)
    def segmentSplitMinutes(self) -> int:
        return self._seg_split_min

    @Property(float, notify=totalMinutesChanged)
    def segmentSplitPct(self) -> float:
        if self._total_min <= 0:
            return 0.0
        return (self._seg_split_min / self._total_min) * 100.0

    @Property(str, notify=sessionTitleChanged)
    def sessionTitle(self) -> str:
        return self._session_title

    @Property(str, notify=campaignTitleChanged)
    def campaignTitle(self) -> str:
        return self._campaign_title

    @Property(str, notify=totalMinutesChanged)
    def segmentsCaption(self) -> str:
        # "2 сегмента · 3ч 47м" — same string the prototype renders.
        h = self._total_min // 60
        m = self._total_min % 60
        return f"2 сегмента · {h}ч {m:02d}м"

    @Slot(result=str)
    def sessionDir(self) -> str:
        """Absolute path of the currently-open session or "".

        Phase 7's MergerWorker needs this to resolve the chat log and
        write merged.txt. Returning a string instead of a Path keeps
        the slot QML-friendly.
        """

        return str(self._session_dir) if self._session_dir is not None else ""

    @Property(float, notify=totalMinutesChanged)
    def totalSeconds(self) -> float:
        """Duration in seconds. MergerWorker uses it to position stitches."""

        return float(self._total_min) * 60.0

    @Slot(str)
    def openSession(self, folder_url_or_path: str) -> None:
        """Load a real session folder. QML drag/drop hands us a file:// URL.

        Derives the session title from the folder name and the
        campaign from its parent. Total duration starts at 0 — an
        earlier version called ffprobe synchronously here, which
        froze the UI thread for N × subprocess-startup-ms and could
        hang indefinitely on a stuck ffprobe (no timeout). Peaks
        extraction already decodes the audio on a background
        QThread (:class:`ui.engines.peaks_worker.PeaksWorker`); the
        worker emits durationReady per track and SessionMeta
        aggregates the max via :meth:`setTotalSeconds` below.
        """

        path = _url_to_path(folder_url_or_path)
        if not path.is_dir():
            return
        self._session_dir = path
        self._session_title = path.name
        parent = path.parent
        self._campaign_title = parent.name if parent and parent.exists() else ""
        self._total_min = 0
        self._seg_split_min = 0

        self.sessionTitleChanged.emit()
        self.campaignTitleChanged.emit()
        self.totalMinutesChanged.emit()
        self.segmentSplitMinutesChanged.emit()
        self.sessionOpened.emit(str(path))

    @Slot(float)
    def setTotalSeconds(self, seconds: float) -> None:
        """Extend the ruler to ``seconds`` if it's longer than current.

        Called from PeaksWorker on a background thread (via
        ``Qt.QueuedConnection``) as each track's duration becomes
        known. Longest wins — one long track sets the session
        length. No setter for shortening; once a duration lands, we
        keep it.
        """

        if seconds <= 0:
            return
        total_min = max(1, int(round(seconds / 60.0)))
        if total_min <= self._total_min:
            return
        self._total_min = total_min
        self._seg_split_min = int(total_min * 2 // 3)
        self.totalMinutesChanged.emit()
        self.segmentSplitMinutesChanged.emit()


# ─────────────────────────────────────────────────────────────────────
# Tracks (one audio lane per player)
# ─────────────────────────────────────────────────────────────────────
TRACK_STATES = ("idle", "queued", "running", "done", "cached", "failed")


@dataclass
class TrackEntry:
    name: str
    role: str              # "GM" | "Игрок" | "Слушатель"
    character: str         # "" for listeners
    excluded: bool         # True when the player has no audio
    model_id: str          # "gigaam" | "faster-whisper" | "whisper-lg" | ""
    model_override: bool
    peaks: list[float] = field(default_factory=list)
    # 0.0 → 1.0 share of this track that has been transcribed. Mutable
    # — AsrWorker emits progress into this via ``TrackListModel
    # .setProgress``. ``0`` means "nothing yet" (idle state).
    progress: float = 0.0
    # Per-track lifecycle state used by the inline status chip:
    #
    #   idle    — no pipeline activity (default)
    #   queued  — scheduled, waiting behind other rows
    #   running — the AsrWorker is attached to this row
    #   done    — ASR finished successfully
    #   cached  — skipped because a result was already on disk
    #   failed  — ASR errored on this row; other rows may still succeed
    state: str = "idle"
    # Set when `state == "failed"` — message shown to the user.
    error_message: str = ""
    # Absolute path to this track's audio file on disk. ``None`` is
    # reserved for tests; PipelineController surfaces the "no audio
    # path" case as a per-track error rather than crashing.
    audio_path: Path | None = None


#: TrackListModel starts empty. Populated only after the user opens
#: a folder — SessionMeta.openSession drives it through sessionOpened.
_TRACK_ROWS: list[TrackEntry] = []


class TrackListModel(QAbstractListModel):
    NameRole      = Qt.ItemDataRole.UserRole + 1
    RoleRole      = Qt.ItemDataRole.UserRole + 2
    CharacterRole = Qt.ItemDataRole.UserRole + 3
    ExcludedRole  = Qt.ItemDataRole.UserRole + 4
    ModelIdRole   = Qt.ItemDataRole.UserRole + 5
    OverrideRole  = Qt.ItemDataRole.UserRole + 6
    PeaksRole     = Qt.ItemDataRole.UserRole + 7
    ProgressRole  = Qt.ItemDataRole.UserRole + 8
    StateRole     = Qt.ItemDataRole.UserRole + 9
    ErrorRole     = Qt.ItemDataRole.UserRole + 10

    _ROLES = {
        NameRole:      b"name",
        RoleRole:      b"playerRole",
        CharacterRole: b"character",
        ExcludedRole:  b"excluded",
        ModelIdRole:   b"modelId",
        OverrideRole:  b"override",
        PeaksRole:     b"peaks",
        ProgressRole:  b"progress",
        StateRole:     b"trackState",
        ErrorRole:     b"errorMessage",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._rows: list[TrackEntry] = list(_TRACK_ROWS)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        t = self._rows[index.row()]
        match role:
            case TrackListModel.NameRole:      return t.name
            case TrackListModel.RoleRole:      return t.role
            case TrackListModel.CharacterRole: return t.character
            case TrackListModel.ExcludedRole:  return t.excluded
            case TrackListModel.ModelIdRole:   return t.model_id
            case TrackListModel.OverrideRole:  return t.model_override
            case TrackListModel.PeaksRole:     return t.peaks
            case TrackListModel.ProgressRole:  return t.progress
            case TrackListModel.StateRole:     return t.state
            case TrackListModel.ErrorRole:     return t.error_message
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name) for role, name in self._ROLES.items()}

    @Slot(result=int)
    def activeCount(self) -> int:
        """Non-excluded tracks — used by the "5 из 6" section header."""
        return sum(1 for t in self._rows if not t.excluded)

    # ── Aggregate progress (for the RunControl dial) ──────────────────
    overallProgressChanged = Signal()

    @Property(float, notify=overallProgressChanged)
    def overallProgress(self) -> float:
        """Mean progress across non-excluded tracks, 0..1.

        With only one worker running in step 5 this averages one live
        value with the zeros of the queued rows — which visually lines
        up with the prototype's aggregate ETA.
        """

        active = [r for r in self._rows if not r.excluded]
        if not active:
            return 0.0
        return sum(r.progress for r in active) / len(active)

    # ── Called from the AsrWorker orchestrator on the main thread ────
    @Slot(int, float)
    def setProgress(self, row: int, progress: float) -> None:
        """Push a 0.0..1.0 progress value to the given row.

        Emits ``dataChanged`` with the ProgressRole only — delegates
        bind only to ``progress`` so peers don't repaint. The setter
        is a ``Slot`` so a worker thread can call it via a queued
        connection without thread-local state leaks.
        """

        if not (0 <= row < len(self._rows)):
            return
        clamped = 0.0 if progress < 0.0 else (1.0 if progress > 1.0 else progress)
        if self._rows[row].progress == clamped:
            return
        self._rows[row].progress = clamped
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [TrackListModel.ProgressRole])
        self.overallProgressChanged.emit()

    @Slot()
    def resetProgress(self) -> None:
        """Zero the progress of every row. Called when the user re-runs
        the pipeline or cancels out of the running state.
        """

        changed = False
        for row in self._rows:
            if row.progress != 0.0:
                row.progress = 0.0
                changed = True
        if changed:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._rows) - 1, 0),
                [TrackListModel.ProgressRole],
            )
            self.overallProgressChanged.emit()

    @Slot(int, str)
    def setState(self, row: int, state: str) -> None:
        """Update the lifecycle state for a single row.

        Known values listed in :const:`TRACK_STATES`. Unknown states
        are rejected to surface mis-spellings early rather than have
        QML silently read them.
        """

        if not (0 <= row < len(self._rows)):
            return
        if state not in TRACK_STATES:
            raise ValueError(f"unknown track state {state!r}; expected one of {TRACK_STATES}")
        if self._rows[row].state == state:
            return
        self._rows[row].state = state
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [TrackListModel.StateRole])

    @Slot(int, str)
    def setError(self, row: int, message: str) -> None:
        """Record a human-readable error for a row (flips state → "failed")."""

        if not (0 <= row < len(self._rows)):
            return
        row_data = self._rows[row]
        row_data.error_message = message
        row_data.state = "failed"
        idx = self.index(row, 0)
        self.dataChanged.emit(
            idx, idx,
            [TrackListModel.StateRole, TrackListModel.ErrorRole],
        )

    # ── Inline edits & per-track model override ──────────────────────
    @Slot(int, str)
    def setPlayerName(self, row: int, name: str) -> None:
        """Rename a player. Empty / whitespace-only names are rejected —
        use a blank placeholder in the UI rather than clearing the row.
        """

        if not (0 <= row < len(self._rows)):
            return
        name = name.strip()
        if not name or self._rows[row].name == name:
            return
        self._rows[row].name = name
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [TrackListModel.NameRole])

    @Slot(int, str)
    def setCharacter(self, row: int, character: str) -> None:
        """Update the character string. Empty strings are allowed and
        render as "Без персонажа" in the row below the name.
        """

        if not (0 <= row < len(self._rows)):
            return
        character = character.strip()
        if self._rows[row].character == character:
            return
        self._rows[row].character = character
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [TrackListModel.CharacterRole])

    @Slot(int, str)
    def setModelOverride(self, row: int, option_id: str) -> None:
        """Pick a model for this row from the override popover.

        Accepted option IDs:
          "default"     — clears the override, uses the active default
          "gigaam"      — GigaAM-v3 (no override flag, same model as default)
          "whisper-med" — whisper medium override
          "whisper-lg"  — whisper large override
        """

        if not (0 <= row < len(self._rows)):
            return
        t = self._rows[row]
        match option_id:
            case "default":
                t.model_id = "gigaam"
                t.model_override = False
            case "gigaam":
                t.model_id = "gigaam"
                t.model_override = False
            case "whisper-med" | "whisper-lg":
                t.model_id = "whisper"
                t.model_override = True
            case _:
                return
        idx = self.index(row, 0)
        self.dataChanged.emit(
            idx, idx,
            [TrackListModel.ModelIdRole, TrackListModel.OverrideRole],
        )

    @Slot()
    def resetStates(self) -> None:
        """Return every row to the ``idle`` state and clear errors.

        Called before a fresh pipeline run. Together with
        :meth:`resetProgress` it's enough to re-enter the idle look.
        """

        changed = False
        for row in self._rows:
            if row.state != "idle" or row.error_message:
                row.state = "idle"
                row.error_message = ""
                changed = True
        if changed:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._rows) - 1, 0),
                [TrackListModel.StateRole, TrackListModel.ErrorRole],
            )

    #: Emitted after :meth:`loadFromDir` has populated rows. Carries
    #: ``[(row, audio_path_str), ...]`` so :mod:`ui.app_qml` can hand
    #: the list to a :class:`PeaksWorker` on a background QThread.
    audioPathsChanged = Signal(list)

    @Slot(str)
    def loadFromDir(self, session_dir_str: str) -> None:
        """Replace rows with one per audio file discovered in ``session_dir``.

        Uses :func:`core.file_matchers.detect_audio_files` — Craig mix-
        down files are skipped automatically. Peaks start empty; the
        shell connects :pysig:`audioPathsChanged` to a peaks worker
        which progressively calls :meth:`setPeaks` per track.

        Connected in :mod:`ui.app_qml` to
        :pysig:`SessionMeta.sessionOpened`.
        """

        session_dir = Path(session_dir_str)
        audio_files = detect_audio_files(session_dir)

        self.beginResetModel()
        self._rows = [
            TrackEntry(
                name=path.stem,
                role="Игрок",
                character="",
                excluded=False,
                model_id="gigaam",
                model_override=False,
                peaks=[],
                audio_path=path,
            )
            for path in audio_files
        ]
        self.endResetModel()
        self.overallProgressChanged.emit()
        self.audioPathsChanged.emit(
            [(i, str(p)) for i, p in enumerate(audio_files)]
        )

    @Slot(int, result=str)
    def audioPathFor(self, row: int) -> str:
        """Return the absolute audio path for ``row`` or "" if unknown.

        Phase 6's PipelineController uses this to hand each AsrWorker
        the file it should transcribe. Tests (no drop yet) return an
        empty string and the worker reports a user-visible error.
        """

        if not (0 <= row < len(self._rows)):
            return ""
        path = self._rows[row].audio_path
        return str(path) if path is not None else ""

    @Slot(int, result=str)
    def modelIdFor(self, row: int) -> str:
        """Return the per-track model_id, empty string for out-of-range."""

        if not (0 <= row < len(self._rows)):
            return ""
        return self._rows[row].model_id

    @Slot(str)
    def appendTrack(self, audio_path_url: str) -> None:
        """Append one audio file to the list (used by the "+ добавить
        аудиодорожку" row). Accepts a ``file://`` URL (QML FileDialog
        emits one) or a plain path.
        """

        path = _url_to_path(audio_path_url)
        if not path.is_file():
            return

        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append(
            TrackEntry(
                name=path.stem,
                role="Игрок",
                character="",
                excluded=False,
                model_id="gigaam",
                model_override=False,
                peaks=[],
                audio_path=path,
            )
        )
        self.endInsertRows()
        self.overallProgressChanged.emit()
        # Trigger peaks extraction for just the new row via the same
        # audioPathsChanged signal shape the shell listens on.
        self.audioPathsChanged.emit([(row, str(path))])

    @Slot(int, list)
    def setPeaks(self, row: int, peaks: list[float]) -> None:
        """Install waveform peaks for one row.

        Called via a queued connection from :class:`PeaksWorker`. A
        ``dataChanged`` emission with the single ``PeaksRole`` tells
        QML to repaint only the affected delegate.
        """

        if not (0 <= row < len(self._rows)):
            return
        self._rows[row].peaks = list(peaks)
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [TrackListModel.PeaksRole])


# ─────────────────────────────────────────────────────────────────────
# Sources (chat log / combat tracker / GM notes lanes above the tracks)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class SourceEntry:
    parser_id: str   # "foundry-chat" | "combat-log" | "plain-text" | "markdown"
    label: str       # short descriptor, e.g. "часть 1"
    file_name: str
    start_pct: float
    end_pct: float


#: SourceListModel also starts empty — populated only after folder drop.
_SOURCE_ROWS: list[SourceEntry] = []


class SourceListModel(QAbstractListModel):
    ParserIdRole = Qt.ItemDataRole.UserRole + 1
    LabelRole    = Qt.ItemDataRole.UserRole + 2
    FileRole     = Qt.ItemDataRole.UserRole + 3
    StartRole    = Qt.ItemDataRole.UserRole + 4
    EndRole      = Qt.ItemDataRole.UserRole + 5

    _ROLES = {
        ParserIdRole: b"parserId",
        LabelRole:    b"label",
        FileRole:     b"fileName",
        StartRole:    b"startPct",
        EndRole:      b"endPct",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._rows: list[SourceEntry] = list(_SOURCE_ROWS)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        s = self._rows[index.row()]
        match role:
            case SourceListModel.ParserIdRole: return s.parser_id
            case SourceListModel.LabelRole:    return s.label
            case SourceListModel.FileRole:     return s.file_name
            case SourceListModel.StartRole:    return s.start_pct
            case SourceListModel.EndRole:      return s.end_pct
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name) for role, name in self._ROLES.items()}

    @Slot(str)
    def loadFromDir(self, session_dir_str: str) -> None:
        """Replace rows with discovered chat logs + combat logs.

        Each match is rendered as a full-width lane (0..100%) because
        precise timeline offsets require timestamp parsing that's out
        of scope until Phase 7 when the merger actually consumes the
        files. The label doubles as the section caption the
        prototype's section header uses.

        Connected in :mod:`ui.app_qml` to
        :pysig:`SessionMeta.sessionOpened`.
        """

        session_dir = Path(session_dir_str)

        new_rows: list[SourceEntry] = []
        for path in detect_fvtt_chat_logs(session_dir):
            new_rows.append(SourceEntry(
                parser_id="foundry-chat",
                label="Foundry чат",
                file_name=path.name,
                start_pct=0.0,
                end_pct=100.0,
            ))
        for path in detect_combat_logs(session_dir):
            new_rows.append(SourceEntry(
                parser_id="combat-log",
                label="Боевой лог",
                file_name=path.name,
                start_pct=0.0,
                end_pct=100.0,
            ))

        self.beginResetModel()
        self._rows = new_rows
        self.endResetModel()
