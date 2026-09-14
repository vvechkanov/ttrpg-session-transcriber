"""Session file discovery helpers."""

from __future__ import annotations

from pathlib import Path


# Чат-лог ищет ``core.file_matchers.detect_fvtt_chat_logs`` — один
# искатель на экран сессии и на мердж. Здесь жил второй, с шаблоном
# ``fvtt-log-*.txt``; он расходился с первым на четырёх осях (дефис,
# любой символ вместо него, регистр имени, регистр расширения), и
# файл, показанный в интерфейсе, молча не доезжал до merged.txt.
# Карточка https://trello.com/c/eyFOj25c .


def find_info_file(session_dir: Path) -> Path | None:
    """session_dir/info.txt if exists, else None."""
    info = session_dir / "info.txt"
    return info if info.exists() else None
