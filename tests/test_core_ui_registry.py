"""Tests for core/ui_registry.py — ленивый резолвер темплейтов.

Покрывают:
  - Зарегистрированный template id есть в ``registered_templates()``
  - ``resolve_template`` на unknown id → KeyError с полезным сообщением
  - Резолвер не крэшится при импорте (ленивость): импорт модуля
    не дёргает импорт ни одного темплейта

В фазах 1-3 шаблонов физически нет, так что тест «известный id
успешно резолвится» здесь **не делается** — это покрытие придёт с
фазы 4, когда появится ``ui/templates/audio_source_template.py``.
"""

from __future__ import annotations

import pytest

from core.ui_contract import UIConfig
from core.ui_registry import (
    _TEMPLATE_MODULE_PATHS,
    registered_templates,
    resolve_template,
)


class TestRegisteredTemplates:
    def test_expected_ids_present(self):
        """MVP шаблоны объявлены в реестре."""
        ids = registered_templates()
        assert "audio_source" in ids
        assert "chat_source" in ids
        assert "merger" in ids
        assert "renderer" in ids

    def test_returns_sorted_tuple(self):
        ids = registered_templates()
        assert isinstance(ids, tuple)
        assert list(ids) == sorted(ids)

    def test_paths_point_under_ui_templates(self):
        """Все зарегистрированные пути лежат в ui.templates.*_template."""
        for template_id, path in _TEMPLATE_MODULE_PATHS.items():
            assert path.startswith("ui.templates."), (
                f"{template_id!r} → {path!r} не в ui.templates/"
            )
            assert path.endswith("_template"), (
                f"{template_id!r} → {path!r} не оканчивается на '_template'"
            )


class TestResolveTemplate:
    def test_unknown_raises_keyerror_with_list(self):
        cfg = UIConfig(template="definitely_not_registered")
        with pytest.raises(KeyError) as exc_info:
            resolve_template(cfg)
        msg = str(exc_info.value)
        assert "definitely_not_registered" in msg
        # сообщение перечисляет известные template id
        assert "audio_source" in msg

    def test_known_but_missing_template_raises_module_not_found(self):
        """В фазе 1 ни одного реального шаблона ещё нет.

        Резолвер зарегистрированного id должен пытаться импортировать
        модуль и падать с понятной ошибкой, а не возвращать None.
        После фазы 4 этот тест нужно будет поменять на assert-что-модуль
        успешно импортируется.
        """
        cfg = UIConfig(template="audio_source")
        with pytest.raises(ModuleNotFoundError):
            resolve_template(cfg)


class TestLazyImport:
    def test_importing_registry_does_not_import_any_template(self):
        """Импорт core.ui_registry не должен эагерно тянуть ui.templates.*.

        Это инвариант, который делает резолвер совместимым с ранними
        фазами миграции и вообще предотвращает круговые импорты.
        """
        import sys

        # Форсим свежий импорт core.ui_registry
        for mod in list(sys.modules):
            if mod.startswith("ui.templates."):
                del sys.modules[mod]
        if "core.ui_registry" in sys.modules:
            del sys.modules["core.ui_registry"]

        import core.ui_registry  # noqa: F401

        loaded_templates = [m for m in sys.modules if m.startswith("ui.templates.")]
        assert loaded_templates == [], (
            f"Эагерный импорт темплейтов: {loaded_templates}"
        )
