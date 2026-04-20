"""Переиспользуемые Qt-виджеты для Session Transcriber.

См. ``docs/architecture/ui-qt-migration.md``. Виджеты в этом пакете —
презентационные (zero module business logic), конфигурируемые через
immutable dataclasses, связь с хостом через Qt Signals. Они могут
импортироваться как хостом (``ui/shell/*``), так и темплейтами
(``ui/templates/*``).
"""

from ui.widgets.source_card import (
    AddSourcePlaceholder,
    AddSourcePlaceholderData,
    CardDisplayState,
    CardStatus,
    SourceCard,
    SourceCardData,
)

__all__ = [
    "AddSourcePlaceholder",
    "AddSourcePlaceholderData",
    "CardDisplayState",
    "CardStatus",
    "SourceCard",
    "SourceCardData",
]
