"""Absolute-time window for the Timeline screen.

This module answers one question: given a session folder with a Craig
``info.txt`` and optional chat / combat files, what absolute time range
should the timeline strip cover, and where on that range does an event
with wall-clock timestamp ``ts`` sit?

The output is a :class:`TimelineWindow` whose :meth:`pct_for` returns a
0..100 value — the position on the ruler as a percentage of the window.

Design notes
------------

* **Pure stdlib.** No PySide6, no project imports from ``sources/``,
  ``mergers/`` or ``ui/``. This module lives in ``core/`` but only
  imports ``datetime``, ``json``, ``re``, ``pathlib``.
* **UTC-only internally.** Callers pass timezone-aware datetimes; the
  parsers normalise to UTC on the way in. Naive datetimes are
  rejected in :meth:`pct_for` (would silently produce wrong percents).
* **All parsers return ``None`` on error**, never raise. The session
  folder on a user's disk is often incomplete or malformed — the
  Timeline screen still renders with a fallback window in that case.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence


# ── Data classes ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CombatMeta:
    """One combat entry parsed from a ``Бой N.txt`` / ``combat*.json`` file.

    Only the fields the timeline needs are stored — no initiative
    order, no per-actor detail. Those are the merger's problem.
    """

    started_at: datetime  # UTC, tz-aware
    ended_at: datetime    # UTC, tz-aware
    label: str            # path.stem, e.g. "Бой 1"


@dataclass(frozen=True)
class TimelineWindow:
    """Absolute time window of the full session timeline.

    ``t_end`` is guaranteed by :func:`build_window` to be strictly
    greater than ``t0`` (at least 10 minutes apart) — :meth:`pct_for`
    relies on ``(t_end - t0).total_seconds() > 0`` for division.
    """

    t0: datetime      # UTC, tz-aware
    t_end: datetime   # UTC, tz-aware, > t0
    #: Когда Craig начал писать. ``None`` — нет ``info.txt``. Отдельно
    #: от ``t0``, потому что запись может начаться позже сессии: чат и
    #: бои живут левее её, и это надо было уметь показать.
    recording_start: datetime | None = None

    @property
    def recording_start_pct(self) -> float:
        """Где на линейке начинается запись. ``0.0`` если старт неизвестен.

        Всё левее этой отметки — материал, у которого нет аудио.
        """
        if self.recording_start is None:
            return 0.0
        return self.pct_for(self.recording_start)

    @property
    def covers_time_before_recording(self) -> bool:
        """``True``, если в окне есть что-то до старта записи."""
        return self.recording_start_pct > 0.0

    def pct_for(self, ts: datetime) -> float:
        """Map an absolute UTC timestamp to a 0..100 position.

        Values outside ``[t0, t_end]`` are clamped. Naive datetimes
        (``tzinfo is None``) raise ``ValueError`` — silent conversion
        of a local time as if it were UTC has bitten us before and is
        exactly the kind of bug a type system cannot catch for us.
        """

        if ts.tzinfo is None:
            raise ValueError(
                "TimelineWindow.pct_for requires a timezone-aware datetime; "
                "got naive datetime — pass UTC explicitly."
            )
        ts_utc = ts.astimezone(timezone.utc)
        total = (self.t_end - self.t0).total_seconds()
        if total <= 0:
            return 0.0
        delta = (ts_utc - self.t0).total_seconds()
        pct = (delta / total) * 100.0
        if pct < 0.0:
            return 0.0
        if pct > 100.0:
            return 100.0
        return pct


# ── Parsers ──────────────────────────────────────────────────────────────


_INFO_START_RE = re.compile(
    r"^\s*start\s+time\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


def parse_info_start(info_path: Path) -> datetime | None:
    """Return Craig recording start time as a UTC datetime, or ``None``.

    Craig's ``info.txt`` has a line like::

        Start time: 2026-04-09T17:21:29.274Z

    We accept any ISO 8601 form ``datetime.fromisoformat`` understands
    (since Python 3.11 that includes ``Z`` as UTC). ``None`` is
    returned when the file is missing, unreadable, or the line is
    absent / malformed.
    """

    try:
        text = info_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None

    for line in text.splitlines():
        match = _INFO_START_RE.match(line)
        if not match:
            continue
        raw = match.group(1).strip()
        # ``fromisoformat`` pre-3.11 doesn't accept ``Z``.
        raw_normalised = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw_normalised)
        except ValueError:
            return None
        if dt.tzinfo is None:
            # Missing TZ — assume UTC (Craig always writes UTC). Rare
            # failure mode; we'd rather render the timeline than error.
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    return None


def parse_combat_file(path: Path) -> CombatMeta | None:
    """Return a :class:`CombatMeta` parsed from ``path``, or ``None``.

    Expects the Foundry-VTT combat-automation export format::

        {
          "started_at": "2026-04-09T19:25:33.183Z",
          "ended_at":   "2026-04-09T20:45:45.523Z",
          ...
        }

    ``None`` on any failure: missing file, invalid JSON, missing or
    unparseable ``started_at`` / ``ended_at`` fields. The ``label``
    is taken from ``path.stem`` so ``Бой 1.txt`` → ``"Бой 1"``.
    """

    try:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None

    try:
        data = json.loads(raw_text)
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    started = _parse_iso_utc(data.get("started_at"))
    ended = _parse_iso_utc(data.get("ended_at"))
    if started is None or ended is None:
        return None
    if ended < started:
        return None

    return CombatMeta(started_at=started, ended_at=ended, label=path.stem)


def _parse_iso_utc(value: object) -> datetime | None:
    """Parse an ISO-8601 string into a UTC datetime. ``None`` on failure."""

    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    raw_normalised = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw_normalised)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def chat_span(
    chat_log_path: Path,
    info_start: datetime | None,
) -> tuple[datetime, datetime] | None:
    """Return ``(first_ts, last_ts)`` UTC of an FVTT chat log, or ``None``.

    FVTT chat exports carry *local* (browser) timestamps. To anchor
    them in UTC we need Craig's recording start time — without it we
    can't resolve the browser's timezone offset. Goes through the same
    ``resolve_tz_offset`` ladder as
    :class:`sources.game_log.fvtt_chat.FvttChatSource`, so the strip on
    the Timeline screen sits where the merger actually put the chat.
    (It used to call ``guess_tz_offset`` directly and could disagree
    with the merger by whole hours.)

    Returns ``None`` when:
        * ``info_start`` is ``None`` (no anchor available);
        * the file is missing, unreadable, or empty of chat entries;
        * parsing raises unexpectedly (defensive — ``None`` beats a
          500-stack-trace in the Timeline screen).
    """

    if info_start is None:
        return None

    # Local import — keeps the module import graph clean for anyone who
    # statically inspects ``core.timeline_window``; breaks a potential
    # circular import if ``sources/`` ever pulls in ``core/`` helpers.
    try:
        from core.fvtt_helpers import session_combat_paths
        from sources.game_log.fvtt_chat import (
            parse_fvtt_log,
            resolve_tz_offset,
        )
    except ImportError:
        return None

    try:
        entries = parse_fvtt_log(chat_log_path)
    except (OSError, UnicodeError, ValueError):
        return None

    if not entries:
        return None

    info_utc = info_start.astimezone(timezone.utc)
    combat_paths = session_combat_paths(chat_log_path)

    try:
        tz_offset = resolve_tz_offset(
            entries, info_utc, combat_paths=combat_paths
        ).offset_hours
    except (TypeError, ValueError):
        return None

    first_local = entries[0]["datetime"]
    last_local = entries[-1]["datetime"]

    first_utc = _local_to_utc(first_local, tz_offset)
    last_utc = _local_to_utc(last_local, tz_offset)
    if first_utc is None or last_utc is None:
        return None

    if last_utc < first_utc:
        first_utc, last_utc = last_utc, first_utc
    return first_utc, last_utc


def display_offset_hours(
    chat_log_path: Path | None, info_start: datetime | None
) -> float:
    """На сколько сдвигать UTC, чтобы показать время так, как его видели.

    Линейка обязана называть тот же час, что стоит в чат-логе у
    пользователя на экране, поэтому смещение берётся из того же
    резолвера, что и у мерджера, — по чат-логу и боевым дампам.

    Без чат-лога брать неоткуда: тогда зона машины, но **на дату
    сессии**, а не на сегодня, иначе зимняя сессия, открытая летом,
    покажет время на час мимо. Совсем без якорей — ``0.0``.
    """
    if chat_log_path is not None and info_start is not None:
        try:
            from core.fvtt_helpers import session_combat_paths
            from sources.game_log.fvtt_chat import parse_fvtt_log, resolve_tz_offset

            entries = parse_fvtt_log(chat_log_path)
            if entries:
                return resolve_tz_offset(
                    entries,
                    info_start.astimezone(timezone.utc),
                    combat_paths=session_combat_paths(chat_log_path),
                ).offset_hours
        except (ImportError, OSError, UnicodeError, TypeError, ValueError):
            pass

    if info_start is None:
        return 0.0
    try:
        offset = info_start.astimezone().utcoffset()
    except (ValueError, OSError):
        return 0.0
    return offset.total_seconds() / 3600 if offset is not None else 0.0


def _local_to_utc(local_dt: datetime, tz_offset_hours: float) -> datetime | None:
    """Convert a naive local-time ``datetime`` to UTC.

    Mirrors the offset-subtraction logic in
    :meth:`sources.game_log.fvtt_chat.FvttChatSource.extract`.
    """

    try:
        utc_naive = local_dt - timedelta(hours=tz_offset_hours)
    except (TypeError, OverflowError):
        return None
    return utc_naive.replace(tzinfo=timezone.utc)


# ── Window builder ───────────────────────────────────────────────────────


#: Minimum window duration (seconds). Windows shorter than this are
#: rejected — a 2-minute timeline is more confusing than helpful; the
#: caller falls back to the legacy 0..100% behaviour instead.
_MIN_WINDOW_SECONDS = 600.0


#: Default window length when no chat / combat data is available.
#: Four hours covers a typical D&D / PF2e session with room on the
#: right for lingering chat after the final encounter.
_DEFAULT_WINDOW_HOURS = 4.0


def build_window(
    info_start: datetime | None,
    max_track_duration: float | None,
    chat: tuple[datetime, datetime] | None,
    combats: Sequence[CombatMeta],
) -> TimelineWindow | None:
    """Compose a :class:`TimelineWindow` from the available anchors.

    Policy (see :doc:`../docs/adr/ADR-016-module-ui-contract.md` — no,
    actually documented only here because 3a is scoped small):

    * ``t0`` = the earliest of ``info_start``, ``chat.first`` and every
      ``combat.started_at``. The recording is one anchor among them,
      not the origin: it can start after the session did.
    * ``t_end = max(info_start + max_track_duration, chat.last,
      max(combat.ended_at), info_start + default_hours)``.
      The default-hours floor prevents a window that's just 2 minutes
      long when the only data point is a lone chat message.
    * Returns ``None`` when no ``t0`` can be inferred, or when the
      resulting window is shorter than :const:`_MIN_WINDOW_SECONDS`.
      Caller falls back to the legacy 0..100% layout.

    ``max_track_duration`` is optional because ``SourceListModel`` doesn't
    know it at the time it builds source rows (peaks/probe still async).
    When it's ``None`` the window relies on chat / combat / default only;
    see the 3a scope note in the plan.
    """

    candidates_start: list[datetime] = []
    if info_start is not None:
        candidates_start.append(info_start.astimezone(timezone.utc))
    if chat is not None:
        candidates_start.append(chat[0].astimezone(timezone.utc))
    for combat in combats:
        candidates_start.append(combat.started_at.astimezone(timezone.utc))

    if not candidates_start:
        return None

    # The window starts at the earliest thing that happened, which is
    # not necessarily the recording. Anchoring t0 on info_start (as this
    # did) assumes chat and combat only ever happen *after* Record is
    # pressed — and when someone hits Record late, everything before it
    # clamps onto 0% instead: the chat bar pretends to start with the
    # audio and an encounter that ended before the recording collapses
    # to zero width. On a real session that drew a whole fight as a
    # one-pixel tick directly underneath a banner announcing it had no
    # audio. Where the recording sits is kept separately, in
    # ``recording_start``, so the UI can shade the part with no sound.
    t0 = min(candidates_start)

    candidates_end: list[datetime] = []
    if info_start is not None and max_track_duration is not None and max_track_duration > 0:
        candidates_end.append(
            info_start.astimezone(timezone.utc) + timedelta(seconds=max_track_duration)
        )
    if chat is not None:
        candidates_end.append(chat[1].astimezone(timezone.utc))
    for combat in combats:
        candidates_end.append(combat.ended_at.astimezone(timezone.utc))
    if info_start is not None:
        candidates_end.append(
            info_start.astimezone(timezone.utc)
            + timedelta(hours=_DEFAULT_WINDOW_HOURS)
        )

    if not candidates_end:
        return None

    t_end = max(candidates_end)

    if (t_end - t0).total_seconds() < _MIN_WINDOW_SECONDS:
        return None

    return TimelineWindow(
        t0=t0,
        t_end=t_end,
        recording_start=(
            info_start.astimezone(timezone.utc) if info_start is not None else None
        ),
    )


__all__ = [
    "CombatMeta",
    "TimelineWindow",
    "parse_info_start",
    "parse_combat_file",
    "chat_span",
    "build_window",
    "display_offset_hours",
]
