"""First-run onboarding flag storage (P2b).

A tiny companion to :mod:`core.recent_sessions` that answers one
question: "has the user ever dismissed the welcome overlay?"

The flag lives in a dedicated JSON file next to the recent-sessions
file so the two concerns stay independent — clearing the recents list
must not re-trigger the onboarding overlay.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.recent_sessions import config_dir

_FLAG_FILE_NAME = "onboarding_state.json"


def _flag_path() -> Path:
    return config_dir() / _FLAG_FILE_NAME


def is_first_run() -> bool:
    """Return ``True`` when the onboarding overlay has never been dismissed.

    A missing or corrupt file counts as first run — we'd rather show
    the welcome card twice than never.
    """
    path = _flag_path()
    if not path.exists():
        return True
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return True
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return True
    if not isinstance(data, dict):
        return True
    return not bool(data.get("onboarded"))


def mark_onboarded() -> None:
    """Persist the flag so :func:`is_first_run` returns ``False`` from now on."""
    path = _flag_path()
    payload = {"onboarded": True}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
