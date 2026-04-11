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

    def test_audio_source_resolves_to_template_module(self):
        """После Phase 4 audio_source_template существует и резолвится.

        Требует PySide6 для импорта шаблона — пропускаем если его нет.
        """
        pytest.importorskip("PySide6")
        cfg = UIConfig(template="audio_source")
        module = resolve_template(cfg)
        assert callable(getattr(module, "make_home_card", None))
        assert callable(getattr(module, "make_settings_panel", None))
        assert callable(getattr(module, "make_runtime_panel", None))

    def test_all_registered_templates_resolve_after_phase_8(self):
        """Phase 8: chat_source / merger / renderer стубы реализованы."""
        pytest.importorskip("PySide6")
        for template_id in ("chat_source", "merger", "renderer"):
            cfg = UIConfig(template=template_id)
            module = resolve_template(cfg)
            assert callable(getattr(module, "make_home_card", None)), (
                f"{template_id}: missing make_home_card"
            )
            assert callable(getattr(module, "make_settings_panel", None)), (
                f"{template_id}: missing make_settings_panel"
            )
            assert callable(getattr(module, "make_runtime_panel", None)), (
                f"{template_id}: missing make_runtime_panel"
            )


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
