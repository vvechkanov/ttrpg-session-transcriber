"""Speaker map helpers for UI consumers.

Two shapes exist in this module:

1. **Rendered flat map** — ``{track_stem: "Player (Character)"}``, produced by
   :func:`load_speaker_map`. Consumed by the ASR pipeline / merge step.
2. **Raw nested map** — ``{track_stem: {"player": ..., "character": ...,
   "role": ...}}``, produced by :func:`load_speaker_map_raw`. Consumed by
   the GUI editor which needs to show individual fields.

Both shapes read from the same on-disk file: ``<session_dir>/speaker_map.json``.
The canonical location is the session folder; a legacy file at project root
is migrated on first GUI load via :func:`migrate_legacy_speaker_map`.

This module lives in ``core/`` so ``ui/`` can import it without reaching
into ``domain/`` directly (honors the dependency rule ``ui → core → ...``).
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from domain.speaker_map import load_speaker_map  # noqa: F401  (public re-export)

logger = logging.getLogger(__name__)

SPEAKER_MAP_FILENAME = "speaker_map.json"


def _project_root() -> Path:
    """Project root = parent of the ``core/`` folder that contains this file."""
    return Path(__file__).resolve().parent.parent


def load_speaker_map_raw(session_dir: Path) -> dict:
    """Load raw nested speaker map from ``session_dir/speaker_map.json``.

    Returns the on-disk nested dict (``{stem: {"player": ..., "character": ...,
    "role": ...}}``) without rendering labels. If the session-local file is
    missing, falls back to ``<project_root>/speaker_map.json`` (legacy
    location) — read-only fallback, nothing is written here. Use
    :func:`migrate_legacy_speaker_map` to actually copy the legacy file.

    Returns an empty dict on missing file, parse errors, or non-dict content.
    """
    candidates = [
        session_dir / SPEAKER_MAP_FILENAME,
        _project_root() / SPEAKER_MAP_FILENAME,
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def save_speaker_map_raw(session_dir: Path, data: dict) -> Path:
    """Save raw nested speaker map to ``session_dir/speaker_map.json``.

    Always writes to the session-local canonical location, never to project
    root. Returns the path that was written.
    """
    path = session_dir / SPEAKER_MAP_FILENAME
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def migrate_legacy_speaker_map(session_dir: Path) -> Path | None:
    """Copy legacy ``<project_root>/speaker_map.json`` into ``session_dir``.

    One-shot migration on first GUI load of a session folder:

    - If ``session_dir/speaker_map.json`` already exists — do nothing, return
      ``None``.
    - Else if ``<project_root>/speaker_map.json`` exists — copy it into the
      session folder and return the new path. The legacy file is **not**
      deleted — the user removes it manually once they confirm the session
      copy works.
    - Else — return ``None``.

    Errors during copy are logged but not raised; migration is best-effort.
    """
    session_path = session_dir / SPEAKER_MAP_FILENAME
    if session_path.exists():
        return None
    legacy_path = _project_root() / SPEAKER_MAP_FILENAME
    if not legacy_path.exists():
        return None
    try:
        shutil.copy2(legacy_path, session_path)
    except OSError:
        logger.warning(
            "Failed to migrate legacy speaker_map from %s to %s",
            legacy_path,
            session_path,
            exc_info=True,
        )
        return None
    logger.warning(
        "Migrated legacy speaker_map to session folder: %s "
        "(legacy file at %s left intact — remove it manually once confirmed)",
        session_path,
        legacy_path,
    )
    return session_path
