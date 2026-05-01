#!/usr/bin/env python3
"""
Parse Foundry VTT chat logs and convert them to timeline segments
compatible with merge_whisperx.py.

Chat log format:
    [M/D/YYYY, H:MM:SS AM/PM] SpeakerName
    Message text (may be multi-line)
    ---------------------------

info.txt provides recording start time in UTC.
Chat log timestamps are in browser-local time.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TS_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{4},\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M)\]\s*(.+)$"
)

SEPARATOR = "---------------------------"

# "Здесь начался Craig" — пользователь оставляет такое сообщение в FVTT chat
# в момент нажатия Record. Local timestamp ↔ UTC Start time из info.txt
# даёт offset точно, без эвристик. Допустимы скобки/слэш перед,
# регистр игнорируется. Примеры: "craig-start", "Craig Start",
# "[craig-start]", "/craig-start", "craig start session 6".
_ANCHOR_MARKER_RE = re.compile(r"^\s*[/\[]?\s*craig[-_ ]?start\b", re.IGNORECASE)

# Реальные UTC-офсеты живут в [-12, +14]. Что-то вне — либо опечатка
# времени, либо маркер от другой записи; не доверяем.
_MAX_REASONABLE_OFFSET_H = 14.0


# ── Parse FVTT log ────────────────────────────────────────────────────

def parse_fvtt_log(path: Path) -> list[dict]:
    """
    Parse an fvtt-log-*.txt file into a list of entries.

    Returns list of {"datetime": datetime (naive, local), "speaker": str, "text": str}
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = text.split(SEPARATOR)

    entries = []
    for block in blocks:
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue

        m = _TS_RE.match(lines[0].strip())
        if not m:
            continue

        ts_str, speaker = m.group(1), m.group(2).strip()
        try:
            dt = datetime.strptime(ts_str, "%m/%d/%Y, %I:%M:%S %p")
        except ValueError:
            continue

        body = "\n".join(ln.strip() for ln in lines[1:]).strip()
        # Skip trivial messages (just "+", whitespace, or empty)
        if not body or body in ("+",):
            continue

        entries.append({"datetime": dt, "speaker": speaker, "text": body})

    return entries


# ── Parse info.txt ────────────────────────────────────────────────────

def parse_info_start_time(path: Path) -> datetime:
    """
    Read 'Start time: <ISO8601>' from info.txt.
    Returns timezone-aware UTC datetime.
    """
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.lower().startswith("start time:"):
            raw = line.split(":", 1)[1].strip()
            # Handle 'Z' suffix and milliseconds
            raw = raw.replace("Z", "+00:00")
            return datetime.fromisoformat(raw)
    raise ValueError(f"'Start time:' not found in {path}")


# ── Timezone auto-detection ───────────────────────────────────────────

def guess_tz_offset(entries: list[dict], recording_start_utc: datetime) -> float:
    """
    Try UTC offsets from -12 to +14 and pick the one where the first
    chat entry falls closest (by absolute distance) to recording start.

    Sign of delta is intentionally ignored: the first FVTT-chat message
    is often sent BEFORE someone hits Record in Craig (pre-game banter,
    initiative rolls). Requiring ``delta >= 0`` made the heuristic pick
    an offset that is off by an hour in this common case.
    """
    if not entries:
        return 0.0

    first_local = entries[0]["datetime"]
    best_offset = 0.0
    best_delta = float("inf")

    for offset_h in range(-12, 15):
        entry_utc = first_local - timedelta(hours=offset_h)
        entry_utc = entry_utc.replace(tzinfo=timezone.utc)
        delta = abs((entry_utc - recording_start_utc).total_seconds())
        if delta < best_delta:
            best_delta = delta
            best_offset = float(offset_h)

    return best_offset


def find_anchor_offset(
    entries: list[dict], recording_start_utc: datetime
) -> float | None:
    """Find a ``craig-start`` marker in chat and derive exact UTC offset.

    The marker's local timestamp directly anchors to Craig's UTC Start
    time — no guessing. Returns nearest-integer hour offset, or ``None``
    if no marker is found or the implied offset is implausible (>14h).
    """
    rec_naive = recording_start_utc.replace(tzinfo=None)
    for entry in entries:
        if not _ANCHOR_MARKER_RE.match(entry["text"]):
            continue
        delta_seconds = (entry["datetime"] - rec_naive).total_seconds()
        offset_h = float(round(delta_seconds / 3600))
        if abs(offset_h) > _MAX_REASONABLE_OFFSET_H:
            return None
        return offset_h
    return None


def system_utc_offset_hours() -> float | None:
    """Current system local UTC offset in hours, or None if unobtainable.

    Uses ``datetime.now().astimezone().utcoffset()`` which respects DST
    on the current date. The export of FVTT chat is almost always done
    on the same machine the user later runs the merge on, so the
    system's tz is the right anchor in 99% of real-world cases.
    """
    try:
        offset = datetime.now().astimezone().utcoffset()
    except Exception:
        return None
    if offset is None:
        return None
    return offset.total_seconds() / 3600


def resolve_tz_offset(
    entries: list[dict],
    recording_start_utc: datetime,
    *,
    override: float | None = None,
) -> tuple[float, str]:
    """Pick the UTC offset for FVTT chat alignment via layered fallback.

    Order (highest priority first):
        1. ``override`` argument — explicit user choice (CLI/UI).
        2. ``find_anchor_offset`` — exact match from a ``craig-start``
           marker in the chat itself.
        3. ``system_utc_offset_hours`` — system local tz.
        4. ``guess_tz_offset`` — heuristic on first entry vs rec start.

    Returns ``(offset_hours, source)`` where ``source`` names the layer
    that won (``"override" | "marker" | "system" | "heuristic"``). The
    source string is meant for log lines so the user can see which
    fallback fired.
    """
    if override is not None:
        return float(override), "override"
    marker = find_anchor_offset(entries, recording_start_utc)
    if marker is not None:
        return marker, "marker"
    sys_tz = system_utc_offset_hours()
    if sys_tz is not None:
        return sys_tz, "system"
    return guess_tz_offset(entries, recording_start_utc), "heuristic"


# ── Convert to merge-compatible segments ──────────────────────────────

def chat_to_segments(
    entries: list[dict],
    recording_start_utc: datetime,
    tz_offset_hours: float,
) -> list[dict]:
    """
    Convert parsed chat entries to segment dicts compatible with merge_whisperx.

    Each segment: {"start", "end", "speaker", "text", "source": "chat"}
    """
    segments = []
    for entry in entries:
        entry_utc = entry["datetime"] - timedelta(hours=tz_offset_hours)
        entry_utc = entry_utc.replace(tzinfo=timezone.utc)
        start = (entry_utc - recording_start_utc).total_seconds()

        if start < 0:
            continue  # before recording started

        segments.append({
            "start": start,
            "end": start + 0.1,
            "speaker": entry["speaker"],
            "text": entry["text"],
            "source": "chat",
        })

    return segments


# ── CLI for standalone testing ────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: parse_fvtt_chat.py <fvtt-log.txt> <info.txt> [tz_offset]")
        sys.exit(1)

    log_path = Path(sys.argv[1])
    info_path = Path(sys.argv[2])
    entries = parse_fvtt_log(log_path)
    rec_start = parse_info_start_time(info_path)

    if len(sys.argv) >= 4:
        tz = float(sys.argv[3])
    else:
        tz = guess_tz_offset(entries, rec_start)
        print(f"Auto-detected timezone: UTC{tz:+.0f}")

    segs = chat_to_segments(entries, rec_start, tz)
    print(f"Parsed {len(entries)} entries -> {len(segs)} segments (within recording)")
    for s in segs[:10]:
        t = s["start"]
        mm, ss = divmod(int(t), 60)
        hh, mm = divmod(mm, 60)
        print(f"  [{hh}:{mm:02d}:{ss:02d}] {s['speaker']}: {s['text'][:80]}")
    if len(segs) > 10:
        print(f"  ... and {len(segs) - 10} more")
