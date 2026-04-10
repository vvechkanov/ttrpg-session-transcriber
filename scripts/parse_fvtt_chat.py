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
    Try UTC offsets from -12 to +14 and pick the one where
    the first chat entry falls closest to (but >= 0) seconds
    from recording start.
    """
    if not entries:
        return 0.0

    first_local = entries[0]["datetime"]
    best_offset = 0.0
    best_delta = float("inf")

    for offset_h in range(-12, 15):
        entry_utc = first_local - timedelta(hours=offset_h)
        entry_utc = entry_utc.replace(tzinfo=timezone.utc)
        delta = (entry_utc - recording_start_utc).total_seconds()
        # We want delta >= 0 (entry after recording start) and as small as possible
        if 0 <= delta < best_delta:
            best_delta = delta
            best_offset = float(offset_h)

    return best_offset


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
