"""Template resolver для Module UI Contract.

Канонический источник — `docs/adr/ADR-016-module-ui-contract.md` §Resolver.

Маппит ``UIConfig.template`` → модуль шаблона из ``ui/templates/``.
**Единственное** место в проекте, где ``core/`` импортирует из ``ui/``
(контролируемый upward-импорт, см. ADR-016 §Layer rules).

Отличие от псевдокода в ADR-016: резолвер **ленивый**. Вместо словаря
``template_id → module_object`` (который требует eager-импорт всех
темплейтов при загрузке ``core/ui_registry``) храним ``template_id →
dotted module path`` и импортируем через ``importlib`` только при
первом резолве. Причина: в фазах 1-3 шаблонов ещё нет — эагер-импорт
ломал бы запуск приложения. После Phase 4 поведение наблюдаемо
идентично: конкретный шаблон загружается один раз и кэшируется
Python'ом в ``sys.modules``.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from core.ui_contract import UIConfig

#: Маппинг идентификатора шаблона → dotted-path модуля. Единственное
#: место, где перечислены все известные шаблоны. Добавление нового
#: шаблона — одна строчка сюда + создание файла в ``ui/templates/``.
_TEMPLATE_MODULE_PATHS: dict[str, str] = {
    "audio_source": "ui.templates.audio_source_template",
    "chat_source":  "ui.templates.chat_source_template",
    "merger":       "ui.templates.merger_template",
    "renderer":     "ui.templates.renderer_template",
}


def resolve_template(ui_config: UIConfig) -> ModuleType:
    """Вернуть модуль шаблона, объявленный в ``ui_config.template``.

    Args:
        ui_config: UIConfig модуля pipeline.

    Returns:
        Импортированный модуль из ``ui/templates/``. Модуль должен
        экспортировать три фабрики: ``make_home_card``,
        ``make_runtime_panel``, ``make_settings_panel``.

    Raises:
        KeyError: если ``ui_config.template`` не зарегистрирован в
            ``_TEMPLATE_MODULE_PATHS``. Сообщение содержит список
            зарегистрированных template id для отладки.
        ModuleNotFoundError: если template id зарегистрирован, но
            соответствующий файл ``ui/templates/<name>_template.py``
            ещё не создан (нормальная ситуация в фазах 1-3 миграции).
    """
    try:
        module_path = _TEMPLATE_MODULE_PATHS[ui_config.template]
    except KeyError as e:
        raise KeyError(
            f"Unknown UI template: {ui_config.template!r}. "
            f"Registered: {sorted(_TEMPLATE_MODULE_PATHS)}"
        ) from e
    return importlib.import_module(module_path)


def registered_templates() -> tuple[str, ...]:
    """Список зарегистрированных template id (отсортирован).

    Полезно для тестов и для дампа в лог при старте приложения.
    """
    return tuple(sorted(_TEMPLATE_MODULE_PATHS))
