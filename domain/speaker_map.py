"""Загрузка и разрешение speaker map'а для Craig-треков."""

import json
from pathlib import Path


def load_speaker_map(session_dir: Path) -> dict[str, str]:
    """Загружает speaker_map.json и возвращает плоский dict ``{track_stem: label}``.

    Порядок поиска (как в ``scripts/merge_whisperx.py`` и
    ``scripts/wisper_launcher.py``):
      1. ``session_dir/speaker_map.json`` — per-session override
      2. ``<project_root>/speaker_map.json`` — shared default

    Каноническая форма записи — вложенный dict вида
    ``{"1-vivienen": {"player": "...", "characters": ["..."], "role": "..."}}``,
    где ``characters`` — список строк (пустой для GM, несколько для мульти-PC).
    Legacy-форма со скаляром ``"character": "..."`` всё ещё читается
    корректно — нормализация в ``core.speaker_map._normalize_entry``
    схлопывает её в ``characters: [...]``. Функция прогоняет каждое
    значение через ту же логику лейбла, что ``merge_whisperx.speaker_label``,
    и возвращает уже отрендеренный label. При любой ошибке чтения/парсинга
    возвращается пустой dict.
    """
    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        session_dir / "speaker_map.json",
        project_root / "speaker_map.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        return {stem: _render_label(stem, entry) for stem, entry in data.items()}
    return {}


def resolve_speaker(track_stem: str, speaker_map: dict[str, str]) -> str:
    """Возвращает label для трека, либо сам stem, если записи нет.

    Порт логики ``merge_whisperx.speaker_label``: пробуем ключ ``stem``,
    затем ``"{stem}.json"``, иначе fallback к ``track_stem``.
    """
    label = speaker_map.get(track_stem) or speaker_map.get(f"{track_stem}.json")
    if label:
        return label
    return track_stem


def _render_label(stem: str, entry: object) -> str:
    """Порт ``merge_whisperx.speaker_label`` для одного raw-значения speaker map.

    Принимает как новую форму (``characters: [...]``), так и legacy
    (``character: "..."``) — legacy превращается в список из одного
    элемента. Пустой список персонажей (GM case) рендерится как просто
    ``"Player"``. Несколько персонажей объединяются через ``" / "``.
    """
    if not isinstance(entry, dict):
        return stem
    player = (entry.get("player") or "").strip()
    raw_characters = entry.get("characters")
    if isinstance(raw_characters, list):
        characters = [
            str(c).strip() for c in raw_characters if isinstance(c, str) and str(c).strip()
        ]
    else:
        legacy = entry.get("character")
        characters = (
            [legacy.strip()] if isinstance(legacy, str) and legacy.strip() else []
        )

    rendered_characters = " / ".join(characters)
    if player and rendered_characters:
        return f"{player} ({rendered_characters})"
    if player:
        return player
    if rendered_characters:
        return rendered_characters
    return stem
