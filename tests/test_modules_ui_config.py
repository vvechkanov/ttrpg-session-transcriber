"""Phase 5: каждый pipeline-модуль объявляет валидный ``ui_config``.

ADR-016 + ADR-017 требуют, чтобы sources / mergers / renderers декларировали
``UIConfig`` как class-атрибут. Хост потом резолвит его через
``core.ui_registry.resolve_template`` — но резолвер падает, если template
id не зарегистрирован или если шаблонный модуль не экспортирует три
фабрики.

Эти тесты — layer-guard: если кто-то добавит новый Source/Merger/Renderer
без ``ui_config`` или с неправильным template id, CI валится здесь.

Тесты НЕ импортируют PySide6 напрямую — но проверка
``resolve_template(...)`` для audio_source подтягивает шаблон, который
зависит от PySide6. Поэтому этот класс тестов ``importorskip("PySide6")``.
"""

from __future__ import annotations

import pytest

from core.ui_contract import UIConfig
from core.ui_registry import resolve_template
from mergers import MERGERS
from renderers import RENDERERS
from sources import SPEECH_SOURCES
from sources.game_log.fvtt_chat import FvttChatSource


# ── Declaration (no Qt required) ─────────────────────────────────────


class TestUIConfigDeclaration:
    """Модули объявляют ``ui_config`` как инстанс ``UIConfig``."""

    def test_all_speech_sources_declare_ui_config(self):
        for name, cls in SPEECH_SOURCES.items():
            assert hasattr(cls, "ui_config"), f"{name}: no ui_config"
            assert isinstance(cls.ui_config, UIConfig), (
                f"{name}: ui_config must be UIConfig instance"
            )

    def test_speech_sources_use_audio_source_template(self):
        for name, cls in SPEECH_SOURCES.items():
            assert cls.ui_config.template == "audio_source", (
                f"{name}: template={cls.ui_config.template!r}"
            )

    def test_speech_sources_declare_backend_param(self):
        """Audio template branches on params['backend']."""
        for name, cls in SPEECH_SOURCES.items():
            backend = cls.ui_config.params.get("backend")
            assert backend in {"gigaam", "whisper"}, (
                f"{name}: params.backend={backend!r}"
            )

    def test_fvtt_chat_declares_chat_source_template(self):
        assert hasattr(FvttChatSource, "ui_config")
        assert FvttChatSource.ui_config.template == "chat_source"

    def test_mergers_declare_merger_template(self):
        for name, cls in MERGERS.items():
            assert hasattr(cls, "ui_config"), f"merger {name}: no ui_config"
            assert cls.ui_config.template == "merger"

    def test_renderers_declare_renderer_template(self):
        for name, cls in RENDERERS.items():
            assert hasattr(cls, "ui_config"), f"renderer {name}: no ui_config"
            assert cls.ui_config.template == "renderer"


# ── Resolver integration (requires Qt) ────────────────────────────────


class TestResolverBridge:
    """``resolve_template`` успешно находит шаблон для каждого модуля.

    Только ``audio_source`` — остальные stub-шаблоны приезжают в Phase 8.
    """

    def test_audio_source_sources_resolve(self):
        pytest.importorskip("PySide6")
        for name, cls in SPEECH_SOURCES.items():
            module = resolve_template(cls.ui_config)
            assert callable(getattr(module, "make_home_card", None)), (
                f"{name}: template missing make_home_card"
            )
            assert callable(getattr(module, "make_settings_panel", None)), (
                f"{name}: template missing make_settings_panel"
            )
            assert callable(getattr(module, "make_runtime_panel", None)), (
                f"{name}: template missing make_runtime_panel"
            )
