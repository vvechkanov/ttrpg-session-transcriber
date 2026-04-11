"""Session file discovery helpers."""

from __future__ import annotations

from pathlib import Path


def find_fvtt_chat_log(session_dir: Path) -> Path | None:
    """First fvtt-log-*.txt in session_dir (alphabetical), or None."""
    matches = sorted(session_dir.glob("fvtt-log-*.txt"))
    return matches[0] if matches else None


def find_info_file(session_dir: Path) -> Path | None:
    """session_dir/info.txt if exists, else None."""
    info = session_dir / "info.txt"
    return info if info.exists() else None
