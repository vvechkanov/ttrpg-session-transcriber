"""Когда началась запись — в тех часах, что видели за столом.

Единственная функция, связывающая относительные ``at`` аннотаций с
настоящим временем. Живёт отдельным модулем, потому что нужна двум
входам сразу: ``core.pipeline`` (CLI) и ``ui.engines.merger_worker``
(GUI). Когда она была приватной внутри pipeline, GUI её просто не
звал — и всё абсолютное время в интерфейсе оказалось мёртвым кодом.

Отдельный модуль ещё и разрывает цикл: ``core.coverage`` импортирует
``core.timeline_window``, так что положить это в любой из них значило
бы связать их между собой.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


def session_clock_start(
    session_dir: Path, chat_log_path: Path | None
) -> datetime | None:
    """Старт записи как aware-datetime в зоне сессии, или ``None``.

    Зона берётся тем же резолвером, что и всё остальное в проекте, — по
    чат-логу и боевым дампам. Без чат-лога брать её неоткуда, кроме как
    у машины; это ступень ``system`` той же лесенки, и она считается
    надёжной, но на дату сессии, а не на сегодня.

    ``None`` — когда сказать нечего: нет ``info.txt``, либо офсет
    оказался лишь угадан. Тогда абсолютного времени у событий не будет
    вовсе, и рендерер обязан обойтись без него. Подставить сюда UTC
    значило бы выдать чужие часы за местные.
    """
    from core.coverage import session_start
    from core.timeline_window import display_offset_hours

    rec_start = session_start(session_dir)
    if rec_start is None:
        return None

    offset = display_offset_hours(chat_log_path, rec_start)
    if offset is None:
        return None

    return rec_start.astimezone(timezone(timedelta(hours=offset)))


__all__ = ["session_clock_start"]
