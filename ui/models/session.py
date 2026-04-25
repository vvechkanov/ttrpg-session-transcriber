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
from datetime import datetime, timedelta
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
    detect_combat_logs,
    detect_craig_segments,
    detect_fvtt_chat_logs,
    match_speaker,
)
from core.peaks import probe_duration
from core.speaker_map import load_speaker_map_raw, migrate_legacy_speaker_map
from core.timeline_window import (
    TimelineWindow,
    build_window,
    chat_span,
    parse_combat_file,
    parse_info_start,
)




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
        # Absolute-time window (Iteration 3a of feature #3). Internal
        # — QML neither reads nor writes this. ``SourceListModel``
        # queries it through :meth:`timelineWindow` when it needs to
        # map combat / chat wall-clock timestamps to percentages.
        # ``None`` means "no window was built" and source rows should
        # fall back to the legacy 0..100% full-width layout.
        self._timeline_window: TimelineWindow | None = None

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
        """Duration caption for the session top bar.

        Returns ``""`` while no duration is known (no session open or
        peaks worker still running). Previously prepended "2 сегмента"
        unconditionally — that was a prototype leftover that lied to
        the user about having detected a Craig split. Segment count
        can be added back once split discovery is implemented.
        """

        if self._total_min <= 0:
            return ""
        h = self._total_min // 60
        m = self._total_min % 60
        return f"{h}ч {m:02d}м"

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
        # Drop any stale window from a previous session — SourceListModel
        # rebuilds it from scratch on the sessionOpened signal below.
        self._timeline_window = None

        self.sessionTitleChanged.emit()
        self.campaignTitleChanged.emit()
        self.totalMinutesChanged.emit()
        self.segmentSplitMinutesChanged.emit()
        self.sessionOpened.emit(str(path))

    def timelineWindow(self) -> TimelineWindow | None:
        """Return the absolute-time window for this session, or ``None``.

        Python-side accessor (not a ``Slot`` — QML has no use for the
        raw datetimes). :class:`SourceListModel` calls this after
        discovery to map combat / chat timestamps to ``startPct`` /
        ``endPct``. ``None`` when no window could be built (e.g. no
        ``info.txt``); callers should fall back to 0..100%.
        """

        return self._timeline_window

    def setTimelineWindow(self, window: TimelineWindow | None) -> None:
        """Store the timeline window for this session.

        Called by :meth:`SourceListModel.loadFromDir` after it builds
        the window from ``info.txt`` + discovered chat / combat files.
        Not a ``Slot``: the type isn't QML-friendly and the UI has no
        business mutating this anyway.
        """

        self._timeline_window = window

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
        # Craig-segment split position is unknown until a real split
        # discovery step lands — we used to fake it as 2/3 of the
        # total, which drew a convincing-looking but fabricated split
        # marker on every fresh session. Leave it at 0 so the ruler
        # and CraigSegmentsStrip hide themselves until a real value
        # comes in.
        self.totalMinutesChanged.emit()


# ─────────────────────────────────────────────────────────────────────
# Tracks (one audio lane per player)
# ─────────────────────────────────────────────────────────────────────
TRACK_STATES = ("idle", "queued", "running", "done", "cached", "failed")


@dataclass(frozen=True)
class TrackSegment:
    """One Craig segment's contribution to a player's row.

    A track in the UI is the union of every Craig-segment slice that
    belongs to one speaker (matched via
    :func:`core.file_matchers.match_speaker`). Feature #4 iteration 4a
    captures the per-segment metadata so a later ASR iteration (4b)
    can run each slice with the right absolute offset.

    ``start_ts`` — wall-clock start of the segment (UTC) pulled from
    that segment's ``info.txt``. ``None`` when the segment has no
    ``info.txt`` or its ``Start time`` line is missing / malformed.

    ``duration_sec`` — probed duration in seconds. Populated only
    when cheaply available; 4a leaves it ``None`` because the ffprobe
    pass moved off the UI thread in an earlier commit and a second
    probe here would re-freeze folder-pick. 4b will either reuse the
    async probe result or drop the field entirely.
    """

    audio_path: Path
    start_ts: datetime | None
    duration_sec: float | None


@dataclass
class TrackEntry:
    name: str
    role: str              # "GM" | "Игрок" | "Слушатель"
    #: Character names this player voices on the row. Multi-character
    #: tracks (one player playing two PCs in the same session) carry a
    #: list with two or more entries; the listener / GM case carries an
    #: empty list. Stored as a list so feature #5's editor popover can
    #: edit each character independently. The ``CharacterDisplayRole``
    #: joins them with `` / `` for read-only rendering.
    characters: list[str] = field(default_factory=list)
    excluded: bool = False  # True when the player has no audio
    #: Per-track ASR model id. Empty string means "use the active
    #: model from :class:`ui.models.model_registry.ModelRegistry`";
    #: non-empty values pin the row to a specific model regardless
    #: of what the user later sets as active.
    model_id: str = ""
    model_override: bool = False
    peaks: list[float] = field(default_factory=list)
    #: Per-segment waveform peaks, parallel to :attr:`segments`. Primary
    #: segment's peaks are mirrored into :attr:`peaks` so legacy code
    #: paths reading the row-level peaks list stay functional. Feature
    #: #4 iter 4b extraction runs once per segment via PeaksWorker.
    peaks_by_segment: list[list[float]] = field(default_factory=list)
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
    #
    # In multi-Craig sessions (feature #4 iter 4a) this points to the
    # *first* segment's audio — the primary file ASR currently runs
    # on. The full per-segment list lives in :attr:`segments`; a later
    # iteration (4b) will drive ASR through every segment.
    audio_path: Path | None = None
    #: All Craig-segment slices that make up this player's timeline,
    #: ordered by ``start_ts`` (unknown starts sorted last). Invariant:
    #: ``len(segments) >= 1`` and ``audio_path == segments[0].audio_path``
    #: for any row built from :meth:`TrackListModel.loadFromDir`. Tests
    #: constructing ``TrackEntry`` directly may leave the list empty.
    segments: tuple[TrackSegment, ...] = ()
    #: True when this row was hydrated from an actual ``speaker_map.json``
    #: entry (vs synthesized from the audio stem on a fresh session).
    #: Drives :attr:`TrackListModel.HasSpeakerMapRole` so the popover
    #: can pre-fill the player field with the saved value rather than
    #: the audio stem placeholder. Flips to ``True`` after a
    #: :meth:`TrackListModel.saveSpeakerMapEntry` round-trip.
    has_speaker_map: bool = False


#: TrackListModel starts empty. Populated only after the user opens
#: a folder — SessionMeta.openSession drives it through sessionOpened.
_TRACK_ROWS: list[TrackEntry] = []


_KNOWN_ROLES: frozenset[str] = frozenset({"GM", "Игрок", "Слушатель"})


def _resolve_speaker_map_entry(
    stem: str,
    raw_map: dict,
) -> tuple[str, str, list[str], bool]:
    """Look up ``stem`` in ``raw_map`` and normalise the entry.

    Returns ``(player_name, role, characters, present)`` where:

      * ``role`` passes through verbatim when it matches one of
        :data:`_KNOWN_ROLES` (``"GM"``, ``"Игрок"``, ``"Слушатель"``).
        Anything else falls back to ``"Игрок"``. The ``"Слушатель"``
        round-trip is what lets a saved listener entry restore the
        ``excluded`` flag on next load.
      * ``present`` is ``True`` only when ``raw_map`` actually contained
        a dict for ``stem``; this drives the ``HasSpeakerMapRole`` model
        flag so the popover can distinguish "fresh row, prefill blank"
        from "previously-saved row, prefill stored player".

    Empty / missing entries return ``("", "Игрок", [], False)`` — the
    model substitutes the audio stem for ``name`` upstream when
    ``player`` is blank. Earlier iterations also tried a ``speaker_key``
    fallback (audio stem with the leading numeric prefix stripped), but
    no real on-disk file used that key shape so the branch was YAGNI
    and got dropped — readers always key by the full audio stem.
    """
    entry = raw_map.get(stem)
    if not isinstance(entry, dict):
        return ("", "Игрок", [], False)
    raw_role = entry.get("role", "")
    role_str = raw_role.strip() if isinstance(raw_role, str) else ""
    role = role_str if role_str in _KNOWN_ROLES else "Игрок"
    raw_player = entry.get("player", "")
    player = raw_player.strip() if isinstance(raw_player, str) else ""
    raw_chars = entry.get("characters")
    characters: list[str]
    if isinstance(raw_chars, list):
        characters = [c for c in raw_chars if isinstance(c, str) and c.strip()]
    else:
        characters = []
    return (player, role, characters, True)


class TrackListModel(QAbstractListModel):
    NameRole              = Qt.ItemDataRole.UserRole + 1
    RoleRole              = Qt.ItemDataRole.UserRole + 2
    CharactersRole        = Qt.ItemDataRole.UserRole + 3
    ExcludedRole          = Qt.ItemDataRole.UserRole + 4
    ModelIdRole           = Qt.ItemDataRole.UserRole + 5
    OverrideRole          = Qt.ItemDataRole.UserRole + 6
    PeaksRole             = Qt.ItemDataRole.UserRole + 7
    ProgressRole          = Qt.ItemDataRole.UserRole + 8
    StateRole             = Qt.ItemDataRole.UserRole + 9
    ErrorRole             = Qt.ItemDataRole.UserRole + 10
    SegmentsRole          = Qt.ItemDataRole.UserRole + 11
    CharacterDisplayRole  = Qt.ItemDataRole.UserRole + 12
    HasSpeakerMapRole     = Qt.ItemDataRole.UserRole + 13

    _ROLES = {
        NameRole:             b"name",
        RoleRole:             b"playerRole",
        CharactersRole:       b"characters",
        ExcludedRole:         b"excluded",
        ModelIdRole:          b"modelId",
        OverrideRole:         b"override",
        PeaksRole:            b"peaks",
        ProgressRole:         b"progress",
        StateRole:            b"trackState",
        ErrorRole:            b"errorMessage",
        SegmentsRole:         b"segments",
        CharacterDisplayRole: b"characterDisplay",
        HasSpeakerMapRole:    b"hasSpeakerMap",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._rows: list[TrackEntry] = list(_TRACK_ROWS)
        #: Optional link back to :class:`SessionMeta`, set by the shell
        #: glue (``ui.app_qml``) before the first folder load. When
        #: present, :attr:`SegmentsRole` resolves each TrackSegment's
        #: ``start_ts`` against :meth:`SessionMeta.timelineWindow` to
        #: produce ``startPct`` / ``endPct`` percentages; otherwise
        #: every row falls back to a single 0..100% segment so the
        #: waveform still renders.
        self._session_meta: SessionMeta | None = None

    def setSessionMeta(self, session_meta: SessionMeta) -> None:
        """Attach the :class:`SessionMeta` this list is bound to.

        Not a ``Slot`` — only Python glue (``ui.app_qml``) ever calls
        this. Used purely to read back the absolute-time
        :class:`TimelineWindow` when computing per-segment percentages
        for the :attr:`SegmentsRole` role.
        """

        self._session_meta = session_meta

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        t = self._rows[index.row()]
        match role:
            case TrackListModel.NameRole:             return t.name
            case TrackListModel.RoleRole:             return t.role
            case TrackListModel.CharactersRole:       return list(t.characters)
            case TrackListModel.CharacterDisplayRole: return " / ".join(t.characters)
            case TrackListModel.ExcludedRole:         return t.excluded
            case TrackListModel.ModelIdRole:          return t.model_id
            case TrackListModel.OverrideRole:         return t.model_override
            case TrackListModel.PeaksRole:            return t.peaks
            case TrackListModel.ProgressRole:         return t.progress
            case TrackListModel.StateRole:            return t.state
            case TrackListModel.ErrorRole:            return t.error_message
            case TrackListModel.SegmentsRole:         return self._segments_payload(t)
            case TrackListModel.HasSpeakerMapRole:    return t.has_speaker_map
        return None

    def _segments_payload(self, entry: TrackEntry) -> list[dict[str, Any]]:
        """Return ``[{"startPct", "endPct", "peaks"}, ...]`` — one per segment.

        Maps each :class:`TrackSegment` to its position on the shared
        absolute-time ruler via the :class:`TimelineWindow` published
        by :class:`SourceListModel` and attaches the per-segment
        waveform peaks from :attr:`TrackEntry.peaks_by_segment`. The
        returned list length always matches ``len(entry.segments)`` (or
        is a single-element fallback when the entry carries no segments
        at all — e.g. a unit-test stub or an explicitly-typed
        ``TrackEntry`` without calling :meth:`loadFromDir`).

        Per-segment fallback to ``{0.0, 100.0}`` triggers when:

            * no :class:`SessionMeta` was attached via
              :meth:`setSessionMeta`, OR
            * the session has no :class:`TimelineWindow` (no
              ``info.txt``, no chat, no combat), OR
            * the specific segment has ``start_ts is None``.

        Each segment's ``endPct`` defaults to 100 when its
        ``duration_sec`` is unknown — 4a doesn't probe durations here
        (that stays on the async ffprobe path) so segments without an
        explicit end extend to the right edge of the ruler.

        The ``peaks`` field carries the segment's waveform; QML renders
        it with a :class:`WaveformCanvas` inside the segment rect.
        Empty list while the peaks worker has not yet landed results
        for that segment — the waveform draws as a flat line.
        """

        if not entry.segments:
            return [{"startPct": 0.0, "endPct": 100.0, "peaks": list(entry.peaks)}]

        window: TimelineWindow | None = None
        if self._session_meta is not None:
            window = self._session_meta.timelineWindow()

        payload: list[dict[str, Any]] = []
        for i, seg in enumerate(entry.segments):
            seg_peaks: list[float] = (
                entry.peaks_by_segment[i]
                if i < len(entry.peaks_by_segment)
                else []
            )
            if window is None or seg.start_ts is None:
                payload.append(
                    {"startPct": 0.0, "endPct": 100.0, "peaks": list(seg_peaks)}
                )
                continue
            start_pct = window.pct_for(seg.start_ts)
            if seg.duration_sec is not None and seg.duration_sec > 0:
                end_ts = seg.start_ts + timedelta(seconds=seg.duration_sec)
                end_pct = window.pct_for(end_ts)
            else:
                end_pct = 100.0
            payload.append(
                {
                    "startPct": start_pct,
                    "endPct": end_pct,
                    "peaks": list(seg_peaks),
                }
            )
        return payload

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name) for role, name in self._ROLES.items()}

    @Slot(result=int)
    def activeCount(self) -> int:
        """Non-excluded tracks — used by the "5 из 6" section header."""
        return sum(1 for t in self._rows if not t.excluded)

    # ── Aggregate progress (for the RunControl dial) ──────────────────
    overallProgressChanged = Signal()
    #: Re-emitted whenever any row's :attr:`TrackEntry.characters` list
    #: changes (load, edit-popover save, manual append). Drives the
    #: ``CastStrip`` QML widget so it can redraw the de-duped union of
    #: every row's character list. Cheap to recompute (≤ a dozen rows
    #: × tiny lists), so we eagerly re-derive on each change rather
    #: than maintain a separate cache.
    aggregatedCharactersChanged = Signal()

    @Property("QStringList", notify=aggregatedCharactersChanged)
    def aggregatedCharacters(self) -> list[str]:
        """De-duped, sorted union of every row's ``characters`` list.

        Empty when no rows or every row carries an empty list (typical
        for fresh sessions before the user pre-populates speaker_map).
        Sorted lexicographically so the strip ordering stays stable
        across edits — alphabetic ordering is the simplest convention
        that doesn't expose iteration order from Python sets.
        """

        seen: set[str] = set()
        for row in self._rows:
            for character in row.characters:
                trimmed = character.strip()
                if trimmed:
                    seen.add(trimmed)
        return sorted(seen)

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
    def updateSpeakerMapRow(
        self,
        row: int,
        player: str,
        role: str,
        characters: list[str],
    ) -> None:
        """Update name / role / characters of a single row in-place.

        Not a ``Slot`` — only Python glue (PipelineController) calls
        this after writing the speaker_map.json file. ``role`` here is
        the speaker_map "GM" / "PC" string; it gets mapped to the
        existing TrackEntry role enum on write.

        Emits ``dataChanged`` for every affected role and
        ``aggregatedCharactersChanged`` so the cast strip re-derives.
        Out-of-range rows are silently ignored to match the existing
        slot conventions on this class.
        """

        if not (0 <= row < len(self._rows)):
            return
        entry = self._rows[row]
        cleaned_player = player.strip()
        # Map speaker_map's wire shape ("GM" / "PC" / "Слушатель") to
        # the TrackEntry role enum ("GM" / "Игрок" / "Слушатель").
        if role == "GM":
            mapped_role = "GM"
        elif role == "Слушатель":
            mapped_role = "Слушатель"
        else:
            mapped_role = "Игрок"
        cleaned_chars = [c.strip() for c in characters if isinstance(c, str) and c.strip()]

        roles_changed: list[int] = []
        if cleaned_player and entry.name != cleaned_player:
            entry.name = cleaned_player
            roles_changed.append(TrackListModel.NameRole)
        if entry.role != mapped_role:
            entry.role = mapped_role
            roles_changed.append(TrackListModel.RoleRole)
        if entry.characters != cleaned_chars:
            entry.characters = cleaned_chars
            roles_changed.extend(
                [TrackListModel.CharactersRole, TrackListModel.CharacterDisplayRole]
            )
        # Saving through the popover always means the row is now backed
        # by a real speaker_map entry — flip the flag so subsequent
        # popover opens prefill the saved player instead of the audio
        # stem placeholder.
        if not entry.has_speaker_map:
            entry.has_speaker_map = True
            roles_changed.append(TrackListModel.HasSpeakerMapRole)

        if roles_changed:
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, roles_changed)
            if TrackListModel.CharactersRole in roles_changed:
                self.aggregatedCharactersChanged.emit()

    @Slot(int, str)
    def setModelOverride(self, row: int, option_id: str) -> None:
        """Pick a model for this row from the override popover.

        Accepted option IDs:
          "default"         — clear override; follow ``ModelRegistry.activeModelId``
          "gigaam"          — pin to GigaAM regardless of active default
          "faster-whisper"  — pin to faster-whisper regardless of active default

        Earlier builds accepted ``"whisper-med"`` / ``"whisper-lg"`` as
        separate options, but every whisper-family id resolved to the
        same ``FasterWhisperSource`` with the single shipped model —
        the size distinction was cosmetic. Those ids are treated as
        legacy aliases for ``"faster-whisper"`` to keep any saved
        per-track state from breaking on first launch after upgrade.
        """

        if not (0 <= row < len(self._rows)):
            return
        t = self._rows[row]
        match option_id:
            case "default":
                t.model_id = ""
                t.model_override = False
            case "gigaam":
                t.model_id = "gigaam"
                t.model_override = True
            case "faster-whisper" | "whisper" | "whisper-med" | "whisper-lg":
                t.model_id = "faster-whisper"
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
    #: ``[(row, seg_idx, audio_path_str), ...]`` so :mod:`ui.app_qml`
    #: can hand the list to a :class:`PeaksWorker` on a background
    #: QThread. Feature #4 iter 4b: one entry per TrackSegment, not
    #: per row — multi-Craig rows fan out into N jobs so every
    #: segment gets its own waveform.
    audioPathsChanged = Signal(list)

    @Slot(str)
    def loadFromDir(self, session_dir_str: str) -> None:
        """Replace rows with one per speaker discovered in ``session_dir``.

        Uses :func:`core.file_matchers.detect_craig_segments` so multi-
        Craig sessions (feature #4 iter 4a) are grouped: the two
        ``1-sir_o_genri`` and ``2-sir_o_genri`` files from separate
        Craig segments collapse into one row with two
        :class:`TrackSegment`\\ s. Single-Craig (flat-layout) sessions
        still produce exactly one row per audio file with a single
        segment — the fallback path in ``detect_craig_segments``
        preserves the pre-feature-#4 behaviour.

        Craig mix-down files are skipped automatically. Peaks start
        empty; the shell connects :pysig:`audioPathsChanged` to a
        peaks worker which progressively calls :meth:`setPeaks` per
        track. 4a emits peaks paths only for the *primary* (first)
        segment of each row — running N-way peaks extraction per row
        is 4b work (the waveform just gets an opacity-50% placeholder
        rect for non-primary segments in QML).

        Connected in :mod:`ui.app_qml` to
        :pysig:`SessionMeta.sessionOpened`.
        """

        session_dir = Path(session_dir_str)
        segments = detect_craig_segments(session_dir)

        # One start_ts per Craig segment — parse once and reuse below.
        segment_starts: list[datetime | None] = [
            parse_info_start(seg.info_path) if seg.info_path is not None else None
            for seg in segments
        ]

        # Group audio files by normalised speaker key (see
        # :func:`match_speaker`) preserving the first-seen ordering
        # inside one segment and the segment order for cross-segment
        # ties. A plain dict keeps insertion order in Python 3.7+.
        grouped: dict[str, list[TrackSegment]] = {}
        for seg_idx, segment in enumerate(segments):
            start_ts = segment_starts[seg_idx]
            for audio_path in segment.audio_files:
                key = match_speaker(audio_path.stem)
                grouped.setdefault(key, []).append(TrackSegment(
                    audio_path=audio_path,
                    start_ts=start_ts,
                    # 4a leaves durations to the async ffprobe pass
                    # (``PeaksWorker.durationReady``); callers needing
                    # end-timestamps should trigger a probe themselves.
                    duration_sec=None,
                ))

        # Feature #5 iter 5b/2: migrate any project-root legacy
        # speaker_map.json into the session folder on first load so
        # the read-side fallback in :func:`load_speaker_map_raw` stops
        # silently masking the missing on-disk copy. ``migrate_legacy_speaker_map``
        # is a no-op when the session file already exists, so re-loads
        # never overwrite user edits.
        migrate_legacy_speaker_map(session_dir)
        # Read speaker_map.json once so each row can be pre-populated
        # with player name / character list / role. Falls back to an
        # empty dict when the file is missing or malformed
        # (``load_speaker_map_raw`` handles both quietly).
        raw_speaker_map = load_speaker_map_raw(session_dir)

        self.beginResetModel()
        new_rows: list[TrackEntry] = []
        seg_jobs: list[tuple[int, int, str]] = []
        for track_segments in grouped.values():
            # Sort by wall-clock start; ``None`` starts drift to the
            # end so fully-unanchored segments don't pretend to be
            # earliest. Stable sort preserves discovery order among
            # equal keys.
            ordered = sorted(
                track_segments,
                key=lambda s: (s.start_ts is None, s.start_ts or datetime.max),
            )
            primary = ordered[0]
            row_idx = len(new_rows)
            stem = primary.audio_path.stem
            entry_name, entry_role, entry_chars, has_map = _resolve_speaker_map_entry(
                stem, raw_speaker_map
            )
            new_rows.append(TrackEntry(
                name=entry_name or stem,
                role=entry_role,
                characters=list(entry_chars),
                # Preserve the listener flag from speaker_map: a
                # round-tripped ``"Слушатель"`` role marks the row as
                # excluded so the pipeline skips it on next run.
                excluded=(entry_role == "Слушатель"),
                model_id="",        # defer to ModelRegistry.activeModelId
                model_override=False,
                peaks=[],
                peaks_by_segment=[[] for _ in ordered],
                audio_path=primary.audio_path,
                segments=tuple(ordered),
                has_speaker_map=has_map,
            ))
            for seg_idx, seg in enumerate(ordered):
                seg_jobs.append((row_idx, seg_idx, str(seg.audio_path)))
        self._rows = new_rows
        self.endResetModel()
        self.overallProgressChanged.emit()
        self.aggregatedCharactersChanged.emit()
        # 4b: one peaks job per TrackSegment. PeaksWorker stores peaks
        # in ``peaks_by_segment`` and mirrors the primary into
        # ``peaks`` so legacy readers continue to work.
        self.audioPathsChanged.emit(seg_jobs)

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

    def segment_offset_seconds(self, segment: TrackSegment) -> float:
        """Seconds between session ``t0`` and this segment's wall-clock start.

        Feeds :class:`ui.engines.asr_worker.SegmentJob.offset_sec` so the
        transcriber can shift each segment's timestamps into the single
        session-wide timeline. Returns ``0.0`` when the session has no
        :class:`TimelineWindow` (no ``info.txt`` + no chat + no combat)
        or the segment itself is unanchored (``start_ts is None``).
        """

        if segment.start_ts is None:
            return 0.0
        if self._session_meta is None:
            return 0.0
        window = self._session_meta.timelineWindow()
        if window is None:
            return 0.0
        return (segment.start_ts - window.t0).total_seconds()

    def segmentsFor(self, row: int) -> list[dict[str, Any]]:
        """Return an ordered list of ``{audioPath, offsetSec, durationSec}``.

        Consumed by :class:`ui.engines.pipeline_controller.PipelineController`
        to build the :class:`SegmentJob` tuple each ASR worker runs on.
        Not a ``Slot`` — the QML layer never reads this directly; the
        only caller is Python-side glue. Empty list for out-of-range
        rows so the controller can surface "no audio" as a per-row error.
        """

        if not (0 <= row < len(self._rows)):
            return []
        entry = self._rows[row]
        segments = entry.segments
        if not segments and entry.audio_path is not None:
            # TrackEntry constructed without segments (test stubs,
            # legacy code paths): synthesize a single entry so callers
            # do not need a special case.
            return [
                {
                    "audioPath": str(entry.audio_path),
                    "offsetSec": 0.0,
                    "durationSec": 0.0,
                }
            ]
        result: list[dict[str, Any]] = []
        for seg in segments:
            result.append(
                {
                    "audioPath": str(seg.audio_path),
                    "offsetSec": self.segment_offset_seconds(seg),
                    "durationSec": float(seg.duration_sec) if seg.duration_sec else 0.0,
                }
            )
        return result

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
        # Manually-added tracks live outside the Craig segment model
        # — they get a single segment with unknown start/duration so
        # the SegmentsRole payload still renders a full-width rect.
        self._rows.append(
            TrackEntry(
                name=path.stem,
                role="Игрок",
                characters=[],
                excluded=False,
                model_id="",        # defer to ModelRegistry.activeModelId
                model_override=False,
                peaks=[],
                peaks_by_segment=[[]],
                audio_path=path,
                segments=(TrackSegment(
                    audio_path=path,
                    start_ts=None,
                    duration_sec=None,
                ),),
            )
        )
        self.endInsertRows()
        self.overallProgressChanged.emit()
        # Manually-appended rows start with no characters but the strip
        # still needs to know the union may have grown (the new row's
        # absence-of-characters can replace a previous row's that got
        # removed in some other flow). Cheap to re-emit.
        self.aggregatedCharactersChanged.emit()
        # Trigger peaks extraction for just the new row via the same
        # audioPathsChanged signal shape the shell listens on. Single-
        # segment drop, so seg_idx is always 0.
        self.audioPathsChanged.emit([(row, 0, str(path))])

    @Slot(int, int, list)
    def setPeaks(self, row: int, seg_idx: int, peaks: list[float]) -> None:
        """Install waveform peaks for one segment of a row.

        Called via a queued connection from :class:`PeaksWorker`. Stores
        peaks in :attr:`TrackEntry.peaks_by_segment` at ``seg_idx`` and,
        when the primary segment lands, also mirrors them into the
        row-level :attr:`TrackEntry.peaks` so legacy readers that only
        look at the primary waveform keep working.

        A ``dataChanged`` emission with ``PeaksRole`` + ``SegmentsRole``
        tells QML to repaint only the affected delegate.
        """

        if not (0 <= row < len(self._rows)):
            return
        entry = self._rows[row]
        # Grow the segment peaks list defensively — tests constructing
        # TrackEntry directly may leave it empty.
        while len(entry.peaks_by_segment) <= seg_idx:
            entry.peaks_by_segment.append([])
        peaks_copy = list(peaks)
        entry.peaks_by_segment[seg_idx] = peaks_copy
        if seg_idx == 0:
            entry.peaks = peaks_copy
        idx = self.index(row, 0)
        self.dataChanged.emit(
            idx,
            idx,
            [TrackListModel.PeaksRole, TrackListModel.SegmentsRole],
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
        #: Optional link back to the owning :class:`SessionMeta`.
        #: Populated via :meth:`setSessionMeta` from :mod:`ui.app_qml`.
        #: When present, :meth:`loadFromDir` publishes the timeline
        #: window it builds so other consumers can read it back.
        self._session_meta: SessionMeta | None = None

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

    def setSessionMeta(self, session_meta: SessionMeta) -> None:
        """Attach the :class:`SessionMeta` instance this list belongs to.

        Not a ``Slot`` — only Python glue (``ui.app_qml``) ever calls
        this. Once attached, :meth:`loadFromDir` writes the built
        :class:`TimelineWindow` back to the meta via
        :meth:`SessionMeta.setTimelineWindow` so other Python code
        (tests, future consumers) can read it.
        """

        self._session_meta = session_meta

    @Slot(str)
    def loadFromDir(self, session_dir_str: str) -> None:
        """Replace rows with discovered chat logs + combat logs.

        Row ``startPct`` / ``endPct`` are now computed against an
        absolute-time :class:`TimelineWindow` (feature #3 iter 3a).
        ``window`` is derived from Craig's ``info.txt`` + the
        discovered chat log span + combat metadata. When no window
        can be built (e.g. ``info.txt`` missing) every row falls back
        to the legacy full-width 0..100% layout so the Timeline
        screen still renders.

        Connected in :mod:`ui.app_qml` to
        :pysig:`SessionMeta.sessionOpened`.
        """

        session_dir = Path(session_dir_str)
        chat_paths = detect_fvtt_chat_logs(session_dir)
        combat_paths = detect_combat_logs(session_dir)

        info_start = parse_info_start(session_dir / "info.txt")

        # Chat span is derived from the *first* chat log only. Real
        # sessions carry at most one fvtt-log-*.txt per export; if
        # more show up later we'd need a policy for merging spans.
        chat_range: tuple | None = None
        if chat_paths:
            chat_range = chat_span(chat_paths[0], info_start)

        combat_metas: list = []
        for combat_path in combat_paths:
            meta = parse_combat_file(combat_path)
            if meta is not None:
                combat_metas.append(meta)

        window = build_window(
            info_start=info_start,
            max_track_duration=None,  # tracks probe asynchronously; 3a ignores them
            chat=chat_range,
            combats=combat_metas,
        )

        # Publish the window back to SessionMeta so other Python-side
        # consumers (tests, future ruler widgets) can read it.
        if self._session_meta is not None:
            self._session_meta.setTimelineWindow(window)

        new_rows: list[SourceEntry] = []
        for path in chat_paths:
            span = chat_span(path, info_start) if window is not None else None
            if window is not None and span is not None:
                start_pct = window.pct_for(span[0])
                end_pct = window.pct_for(span[1])
            else:
                start_pct, end_pct = 0.0, 100.0
            new_rows.append(SourceEntry(
                parser_id="foundry-chat",
                label="Foundry чат",
                file_name=path.name,
                start_pct=start_pct,
                end_pct=end_pct,
            ))

        # Re-parse each combat file so row order matches ``combat_paths``
        # (discovery order). ``combat_metas`` filtered failures; we want
        # to still render a full-width row for malformed combats so the
        # user can tell something's off.
        for path in combat_paths:
            meta = parse_combat_file(path)
            if window is not None and meta is not None:
                start_pct = window.pct_for(meta.started_at)
                end_pct = window.pct_for(meta.ended_at)
            else:
                start_pct, end_pct = 0.0, 100.0
            new_rows.append(SourceEntry(
                parser_id="combat-log",
                label="Боевой лог",
                file_name=path.name,
                start_pct=start_pct,
                end_pct=end_pct,
            ))

        self.beginResetModel()
        self._rows = new_rows
        self.endResetModel()
