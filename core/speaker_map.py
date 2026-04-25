"""Speaker map helpers for UI consumers.

Two shapes exist in this module:

1. **Rendered flat map** — ``{track_stem: "Player (Character)"}``, produced by
   :func:`load_speaker_map`. Consumed by the ASR pipeline / merge step.
2. **Raw nested map** — ``{track_stem: {"player": ..., "characters": [...],
   "role": ...}}``, produced by :func:`load_speaker_map_raw`. Consumed by
   the GUI editor which needs to show individual fields.

Both shapes read from the same on-disk file: ``<session_dir>/speaker_map.json``.
The canonical location is the session folder; a legacy file at project root
is migrated on first GUI load via :func:`migrate_legacy_speaker_map`.

This module lives in ``core/`` so ``ui/`` can import it without reaching
into ``domain/`` directly (honors the dependency rule ``ui → core → ...``).

Schema evolution
----------------
The on-disk nested shape has two accepted forms:

- **New canonical** — ``{"player": "Alice", "characters": ["Aragorn"], "role": "PC"}``
  Supports multi-character tracks (``["Одетт", "Lyra"]``) and GM
  (``characters: []``).
- **Legacy accepted** — ``{"player": "Alice", "character": "Aragorn", "role": "PC"}``
  Older single-string field. Readers normalize it on load; writers never
  emit it. The on-disk legacy file is **not** rewritten silently — it
  stays in its old shape until the user saves via the editor.
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


def _normalize_entry(raw: object) -> dict:
    """Normalize a single raw speaker_map entry to canonical shape.

    Canonical shape: ``{"player": str, "characters": list[str], "role": str}``.

    Accepts either the new ``characters: [...]`` list or the legacy
    ``character: "..."`` single string. Empty / whitespace-only strings
    are stripped from the list (so ``character: ""`` yields
    ``characters: []``, which is how we encode the GM case). Non-string
    elements in ``characters`` are dropped (not coerced) to avoid
    accidental ``"42"`` labels leaking into the UI. A malformed scalar
    ``characters: "Aragorn"`` (string instead of list) is wrapped into
    ``["Aragorn"]`` — robust over strict.

    Non-string ``player`` / ``role`` coerce to ``""`` (safer to render
    than ``"None"``).

    Unknown keys are preserved verbatim — future fields like ``note``,
    ``color``, ``tags`` pass through. The legacy ``character`` key is
    the one exception: it gets collapsed into ``characters`` and dropped
    from the output.

    Non-dict inputs are coerced into an empty canonical entry.
    """
    if not isinstance(raw, dict):
        return {"player": "", "characters": [], "role": ""}

    extras = {
        k: v
        for k, v in raw.items()
        if k not in ("player", "character", "characters", "role")
    }

    raw_player = raw.get("player")
    player = raw_player.strip() if isinstance(raw_player, str) else ""
    raw_role = raw.get("role")
    role = raw_role.strip() if isinstance(raw_role, str) else ""

    characters: list[str]
    raw_characters = raw.get("characters")
    if isinstance(raw_characters, list):
        # Trust the new-shape list; strip empty / whitespace-only entries
        # and drop non-string elements (don't coerce — avoids "42" labels).
        characters = [
            c.strip() for c in raw_characters if isinstance(c, str) and c.strip()
        ]
    elif isinstance(raw_characters, str):
        # Malformed scalar where a list was expected — wrap, don't drop.
        stripped = raw_characters.strip()
        characters = [stripped] if stripped else []
    else:
        # Fallback to legacy single-string `character` field.
        legacy = raw.get("character")
        if isinstance(legacy, str) and legacy.strip():
            characters = [legacy.strip()]
        else:
            characters = []

    return {**extras, "player": player, "characters": characters, "role": role}


def load_speaker_map_raw(session_dir: Path) -> dict:
    """Load raw nested speaker map from ``session_dir/speaker_map.json``.

    Returns a nested dict in the **new canonical shape**
    (``{stem: {"player": str, "characters": list[str], "role": str}}``).
    If the on-disk file uses the legacy ``character: "..."`` form, it is
    normalized in memory only — the file on disk is **not** rewritten
    silently (callers that want to persist normalization must call
    :func:`save_speaker_map_raw` explicitly).

    If the session-local file is missing, falls back to
    ``<project_root>/speaker_map.json`` (legacy location) — read-only
    fallback, nothing is written here. Use :func:`migrate_legacy_speaker_map`
    to actually copy the legacy file.

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
            return {stem: _normalize_entry(entry) for stem, entry in data.items()}
    return {}


def save_speaker_map_raw(session_dir: Path, data: dict) -> Path:
    """Save raw nested speaker map to ``session_dir/speaker_map.json``.

    Always writes to the session-local canonical location, never to project
    root. The caller usually passes an already-normalized dict, but we
    defensively re-normalize each entry so legacy-shape input still
    produces a **new-shape** file on disk. Returns the path that was
    written.
    """
    path = session_dir / SPEAKER_MAP_FILENAME
    normalized = {stem: _normalize_entry(entry) for stem, entry in data.items()}
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
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
