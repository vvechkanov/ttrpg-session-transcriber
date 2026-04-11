"""Tests for core/ui_contract.py — UIConfig dataclass + SettingsPanelProtocol.

Покрывают контракт из ADR-016:
  - UIConfig frozen, params default {}, visible default True
  - SettingsPanelProtocol runtime_checkable
  - duck-typed объект проходит isinstance-проверку

Не требуют PySide6 — namespace ``core/ui_contract.py`` обязан быть
свободен от GUI-импортов (см. ADR-016 §Layer rules).
"""

from __future__ import annotations

import dataclasses

import pytest

from core.ui_contract import SettingsPanelProtocol, UIConfig


class TestUIConfig:
    def test_minimal_construction(self):
        cfg = UIConfig(template="audio_source")
        assert cfg.template == "audio_source"
        assert cfg.params == {}
        assert cfg.visible is True

    def test_full_construction(self):
        cfg = UIConfig(
            template="audio_source",
            params={"show_hotwords": True, "precision_options": ("fp32", "int8")},
            visible=False,
        )
        assert cfg.template == "audio_source"
        assert cfg.params == {"show_hotwords": True, "precision_options": ("fp32", "int8")}
        assert cfg.visible is False

    def test_frozen(self):
        """ADR-016: UIConfig — frozen dataclass."""
        cfg = UIConfig(template="audio_source")
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.template = "chat_source"  # type: ignore[misc]

    def test_params_default_is_per_instance(self):
        """Два UIConfig без params не шарят один dict (default_factory)."""
        a = UIConfig(template="a")
        b = UIConfig(template="b")
        assert a.params is not b.params

    def test_equality_by_value(self):
        a = UIConfig(template="x", params={"k": 1})
        b = UIConfig(template="x", params={"k": 1})
        assert a == b

    def test_hash_requires_hashable_params(self):
        """Frozen dataclass hashable только если все поля hashable.

        params — dict, он НЕ hashable → UIConfig не hashable.
        Документируем это поведение: если понадобится UIConfig в set/dict
        key, нужно будет либо заменить params на FrozenMapping/tuple-of-pairs,
        либо вычислять hash вручную.
        """
        cfg = UIConfig(template="x")
        with pytest.raises(TypeError):
            hash(cfg)


class TestSettingsPanelProtocol:
    def test_runtime_checkable(self):
        """ADR-016: Protocol помечен @runtime_checkable."""

        class GoodPanel:
            changed = object()  # stand-in for Signal

            def validate(self) -> list[str]:
                return []

            def apply_changes(self) -> None:
                pass

            def has_unsaved_changes(self) -> bool:
                return False

        assert isinstance(GoodPanel(), SettingsPanelProtocol)

    def test_missing_method_fails_isinstance(self):
        class BadPanel:
            changed = object()

            def validate(self) -> list[str]:
                return []

            # no apply_changes, no has_unsaved_changes

        assert not isinstance(BadPanel(), SettingsPanelProtocol)

    def test_plain_object_fails_isinstance(self):
        assert not isinstance(object(), SettingsPanelProtocol)
