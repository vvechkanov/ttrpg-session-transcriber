"""Загрузка и разрешение speaker map'а для Craig-треков."""

import json
from pathlib import Path


def load_speaker_map(session_dir: Path) -> dict[str, str]:
    """Загружает speaker_map.json и возвращает плоский dict ``{track_stem: label}``.

    Порядок поиска (как в ``scripts/merge_whisperx.py`` и
    ``scripts/wisper_launcher.py``):
      1. ``session_dir/speaker_map.json`` — per-session override
      2. ``<project_root>/speaker_map.json`` — shared default

    Исходный файл — вложенный dict вида
    ``{"1-vivienen": {"player": "...", "character": "...", "role": "..."}}``.
    Функция прогоняет каждое значение через ту же логику, что
    ``merge_whisperx.speaker_label``, и возвращает уже отрендеренный label.
    При любой ошибке чтения/парсинга возвращается пустой dict.
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
    """Порт ``merge_whisperx.speaker_label`` для одного raw-значения speaker map."""
    if not isinstance(entry, dict):
        return stem
    player = (entry.get("player") or "").strip()
    character = (entry.get("character") or "").strip()
    if player and character:
        return f"{player} ({character})"
    if player:
        return player
    if character:
        return character
    return stem
