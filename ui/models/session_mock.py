"""Mock data for the Timeline idle-phase slice.

The prototype's timeline is populated with a hard-coded 3h47m session
(6 players, 3 extra sources, Craig split at 2h30m). This module
mirrors that data so the layout-focused Python ↔ QML pipeline has
something to render without requiring real session discovery.

When real session ingestion arrives (step 5+), ``TrackListModel`` and
``SourceListModel`` stay with the same role names — only the data
source changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    Property,
    Signal,
    Slot,
)


# Total session duration and the point at which Craig split the
# recording into two segments. The ruler and the Craig-segments strip
# both read these.
TOTAL_MIN: int = 227        # 3h47m
SEG_SPLIT_MIN: int = 150    # 2h30m

SEG1_END_PCT: float = (SEG_SPLIT_MIN / TOTAL_MIN) * 100.0  # ~66%


class SessionMeta(QObject):
    """Scalar session facts shared by the ruler, waveforms, and strip.

    Exposed to QML as ``sessionMeta``. Values are read-only at this
    stage — the real SessionModel that arrives with ingest will
    replace this with a signal-driven version.
    """

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._total_min = TOTAL_MIN
        self._seg_split_min = SEG_SPLIT_MIN

    @Property(int, constant=True)
    def totalMinutes(self) -> int:
        return self._total_min

    @Property(int, constant=True)
    def segmentSplitMinutes(self) -> int:
        return self._seg_split_min

    @Property(float, constant=True)
    def segmentSplitPct(self) -> float:
        return (self._seg_split_min / self._total_min) * 100.0

    @Property(str, constant=True)
    def sessionTitle(self) -> str:
        return "Сессия 14 — Битва на мосту"

    @Property(str, constant=True)
    def campaignTitle(self) -> str:
        return "Storm King's Thunder"

    @Property(str, constant=True)
    def segmentsCaption(self) -> str:
        # "2 сегмента · 3ч 47м" — same string the prototype renders.
        h = self._total_min // 60
        m = self._total_min % 60
        return f"2 сегмента · {h}ч {m:02d}м"


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
    model_id: str          # "gigaam" | "whisper" | ""
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


def _gen_peaks(seed: int, count: int = 80) -> list[float]:
    """Deterministic pseudo-peaks — same shape the prototype uses.

    Matches ``genActivity`` in the HTML file so the visual outcome is
    recognisable when the screens are compared side-by-side.
    """

    x = seed * 9301 + 49297
    out: list[float] = []
    for i in range(count):
        x = (x * 9301 + 49297) % 233280
        r = x / 233280
        base = 0.2 + r * 0.7
        gap = 0.05 if i in (12, 30, 55) else 1.0
        out.append(max(0.04, base * gap))
    return out


_TRACK_ROWS: list[TrackEntry] = [
    TrackEntry("Andrey", "GM",        "Гендальф",    False, "gigaam",  False, _gen_peaks(1)),
    TrackEntry("Boris",  "Игрок",     "Арагорн",     False, "gigaam",  False, _gen_peaks(2)),
    TrackEntry("Carol",  "Игрок",     "Лютиэн",      False, "whisper", True,  _gen_peaks(3)),
    TrackEntry("Dmitry", "Слушатель", "",            True,  "",        False, _gen_peaks(4)),
    TrackEntry("Eve",    "Игрок",     "Галадриэль",  False, "gigaam",  False, _gen_peaks(5)),
    TrackEntry("Frank",  "Игрок",     "Боромир",     False, "gigaam",  False, _gen_peaks(6)),
]


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


_SOURCE_ROWS: list[SourceEntry] = [
    SourceEntry("foundry-chat", "часть 1",    "session-14-chat-part1.db", 0.0,           SEG1_END_PCT),
    SourceEntry("foundry-chat", "часть 2",    "session-14-chat-part2.db", SEG1_END_PCT,  100.0),
    SourceEntry("combat-log",   "Гоблины",    "combat-goblins.json",      36.0,          60.0),
]


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
