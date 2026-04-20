"""Persistent storage for the "Recent sessions" list on the empty state.

Pure stdlib module — no Qt, no UI imports. The UI layer
(``ui/shell/screens/empty_state_screen.py``) is presentation-only and
receives a :class:`tuple[RecentSession, ...]` via constructor /
:meth:`refresh_recent`. :class:`ui.shell.app.MainWindow` is the host
that pushes updates through.

Storage location:
    * Windows — ``%LOCALAPPDATA%/TTRPG-Session-Transcriber/recent_sessions.json``
    * other OSes — ``~/.config/ttrpg-session-transcriber/recent_sessions.json``

File format is a tiny hand-rolled JSON object; readers tolerate a
missing / corrupt file by returning an empty tuple. Entries whose
on-disk path no longer exists are skipped at load time so the UI never
shows a broken "recent" row.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

#: Maximum number of entries persisted in the recent-sessions list.
#: UI shows them newest-first. When the list is full and a new session
#: is added, the oldest is dropped.
MAX_RECENT = 5

_APP_DIR_WINDOWS = "TTRPG-Session-Transcriber"
_APP_DIR_XDG = "ttrpg-session-transcriber"
_RECENT_FILE_NAME = "recent_sessions.json"


@dataclass(frozen=True)
class RecentSession:
    """A single entry in the recent-sessions list.

    Attributes:
        path: Absolute path to the session folder.
        opened_at: Unix epoch seconds the session was last opened.
    """

    path: Path
    opened_at: float


def config_dir() -> Path:
    """Return the per-user config directory, creating it if missing.

    On Windows honors ``%LOCALAPPDATA%`` (falls back to
    ``~/AppData/Local`` if that env var is absent). On other platforms
    uses XDG-style ``~/.config/ttrpg-session-transcriber``.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            root = Path(base) / _APP_DIR_WINDOWS
        else:
            root = Path.home() / "AppData" / "Local" / _APP_DIR_WINDOWS
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            root = Path(xdg) / _APP_DIR_XDG
        else:
            root = Path.home() / ".config" / _APP_DIR_XDG
    root.mkdir(parents=True, exist_ok=True)
    return root


def _store_path() -> Path:
    return config_dir() / _RECENT_FILE_NAME


def load_recent() -> tuple[RecentSession, ...]:
    """Load the recent-sessions list from disk.

    Returns an empty tuple when:
        * the file does not exist;
        * the file is corrupt / malformed JSON;
        * the top-level JSON shape is wrong.

    Entries whose ``path`` no longer exists on disk are silently
    dropped — the list shown to the user should never have dead rows.
    """
    path = _store_path()
    if not path.exists():
        return ()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return ()
    if not isinstance(data, dict):
        return ()
    entries = data.get("sessions")
    if not isinstance(entries, list):
        return ()

    result: list[RecentSession] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        path_str = item.get("path")
        opened_at = item.get("opened_at")
        if not isinstance(path_str, str):
            continue
        if not isinstance(opened_at, (int, float)):
            continue
        entry_path = Path(path_str)
        if not entry_path.exists():
            continue
        result.append(
            RecentSession(path=entry_path, opened_at=float(opened_at))
        )
    return tuple(result)


def _persist(sessions: tuple[RecentSession, ...]) -> None:
    """Write ``sessions`` to the JSON file atomically."""
    path = _store_path()
    payload = {
        "sessions": [
            {"path": str(s.path), "opened_at": float(s.opened_at)}
            for s in sessions
        ]
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def add_recent(session_dir: Path) -> tuple[RecentSession, ...]:
    """Prepend ``session_dir`` to the persisted list.

    Behaviour:
        * Resolves ``session_dir`` to an absolute path for dedupe.
        * If the same path is already in the list, its previous entry
          is dropped — the new timestamp wins.
        * The list is truncated to :data:`MAX_RECENT` newest entries.
        * The file is created on first call.

    Returns:
        The new list (newest first) as it was just persisted.
    """
    try:
        resolved = session_dir.resolve()
    except OSError:
        resolved = session_dir

    existing = load_recent()
    deduped: list[RecentSession] = []
    for entry in existing:
        try:
            entry_resolved = entry.path.resolve()
        except OSError:
            entry_resolved = entry.path
        if entry_resolved == resolved:
            continue
        deduped.append(entry)

    new_entry = RecentSession(path=resolved, opened_at=time.time())
    new_list = (new_entry, *deduped)[:MAX_RECENT]
    _persist(new_list)
    return new_list


def clear_recent() -> None:
    """Delete the recent-sessions file.

    A subsequent :func:`load_recent` returns ``()``. No-op if the file
    does not exist.
    """
    path = _store_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        # Best-effort: overwrite with an empty payload so load_recent
        # still returns () on the next call.
        _persist(())
