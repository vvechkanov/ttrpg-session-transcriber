"""Module UI Contract — нейтральные типы между модулями pipeline и UI.

Канонический источник — `docs/adr/ADR-016-module-ui-contract.md`.

Этот файл не импортирует PySide6, ui.* или sources.*. Он — единственное,
что разрешено импортировать модулям `sources/`, `mergers/`, `renderers/`,
`domain/` из UI-контракта. Любой другой UI-импорт из этих слоёв — нарушение
архитектурных инвариантов (см. ADR-016 §Layer rules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class UIConfig:
    """Декларативная UI-привязка модуля pipeline.

    Модуль (source/merger/renderer) объявляет это как атрибут класса::

        class GigaAMSource:
            ui_config = UIConfig(
                template="audio_source",
                params={"show_hotwords": True, "precision_options": ("fp32", "int8")},
            )

    Модуль НЕ импортирует PySide6 и НЕ импортирует из ``ui/``.
    """

    #: Идентификатор шаблона в ``ui/templates/``. Резолвится через
    #: ``core.ui_registry.resolve_template``. Примеры: ``"audio_source"``,
    #: ``"chat_source"``, ``"merger"``, ``"renderer"``.
    template: str

    #: Параметры для шаблона. Feature-флаги, опции, преднастроенные
    #: значения селекторов. Шаблон читает этот словарь и решает, какие
    #: поля показывать и с какими опциями.
    params: dict[str, Any] = field(default_factory=dict)

    #: Если ``False`` — модуль выполняется в pipeline, но не показывается
    #: на экране. Используется для фоновых post-processor'ов, debug-хуков,
    #: telemetry-коллекторов. По умолчанию ``True``.
    visible: bool = True


@runtime_checkable
class SettingsPanelProtocol(Protocol):
    """Контракт виджета, возвращаемого ``make_settings_panel``.

    Хост (``ui/shell/settings_drawer.py``) полагается только на эти
    члены. Виджет реализуется в ``ui/templates/<name>_template.py`` и
    может быть любым ``QWidget``-ом — важно только наличие ``changed``
    сигнала и трёх методов.

    Жизненный цикл:

    1. Пользователь кликает ``[Настроить]`` → шелл вызывает
       ``make_settings_panel(...)`` темплейта и получает ``panel``.
    2. Шелл подключается к ``panel.changed`` → при каждом сигнале
       перерисовывает dirty-индикатор в footer'е drawer'а.
    3. Клик ``[Сохранить]`` → шелл вызывает ``panel.validate()``.
       Пусто → ``panel.apply_changes()`` → drawer закрывается.
       Непусто → шелл показывает ошибки, save заблокирован, drawer
       остаётся открытым.
    4. Клик ``[Отмена]`` / Esc / scrim → шелл проверяет
       ``panel.has_unsaved_changes()``. True → модальное
       подтверждение. False → закрытие без вопросов.
    """

    #: PySide6 ``Signal`` без аргументов. Шаблон эмитит его при каждом
    #: изменении любого поля формы (checkbox, text change, slider).
    #: Хост слушает для подсветки dirty-индикатора и активации кнопки
    #: ``[Сохранить]``. Объявлен как ``Any`` — Protocol+Signal плохо
    #: типизируется во всех версиях mypy, runtime-проверка не требуется.
    changed: Any

    def validate(self) -> list[str]:
        """Вернуть список текстовых ошибок.

        Пустой список = форма валидна, можно вызывать ``apply_changes``.
        Непустой = хост показывает ошибки под формой и блокирует Save.
        Вызывается хостом при клике на ``[Сохранить]``, ДО
        ``apply_changes``.
        """

    def apply_changes(self) -> None:
        """Записать значения полей в модуль.

        Вызывается хостом после успешного ``validate()``. После возврата
        хост закрывает drawer и считает ``has_unsaved_changes()`` за
        False. Метод должен быть идемпотентен.
        """

    def has_unsaved_changes(self) -> bool:
        """Есть ли незафиксированные изменения.

        Используется хостом при закрытии drawer'а (Esc / scrim /
        ``[Отмена]`` / закрытие окна) — если True, показывается диалог
        «Сохранить изменения?».
        """
