"""Phase 8 — smoke tests for stub templates (chat / merger / renderer).

Each template exports three factories; we just verify they return
widgets that implement ``SettingsPanelProtocol`` and that the basic
lifecycle (construct → validate → apply_changes → has_unsaved_changes)
doesn't raise. Full UX coverage is deferred — these are stubs for
Phase 8 and will be rewritten when more modules ship.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from core.ui_contract import SettingsPanelProtocol
from ui.templates import (
    chat_source_template,
    merger_template,
    renderer_template,
)


class _FakeFvtt:
    name = "fvtt-chat"
    tz_offset: float | None = None


class _FakeMerger:
    gap_sec = 1.0


class _FakeRenderer:
    pass


def _noop_state(*_: Any) -> None:
    return None


# ── chat_source ───────────────────────────────────────────────────────


@pytest.mark.gui
class TestChatSourceTemplate:
    def test_exports_three_factories(self):
        assert callable(chat_source_template.make_home_card)
        assert callable(chat_source_template.make_settings_panel)
        assert callable(chat_source_template.make_runtime_panel)

    def test_home_card_builds(self, qtbot, tmp_path: Path):
        state = chat_source_template.ChatSourceState(session_dir=tmp_path)
        card = chat_source_template.make_home_card(
            parent=None, module=_FakeFvtt(), state=state, params={}
        )
        qtbot.addWidget(card)

    def test_settings_panel_protocol_and_roundtrip(self, qtbot, tmp_path: Path):
        fake = _FakeFvtt()
        state = chat_source_template.ChatSourceState(session_dir=tmp_path)
        panel = chat_source_template.make_settings_panel(
            parent=None, module=fake, state=state, params={}
        )
        qtbot.addWidget(panel)

        assert isinstance(panel, SettingsPanelProtocol)
        assert panel.validate() == []
        assert panel.has_unsaved_changes() is False

        panel._tz_spin.setValue(3.0)  # noqa: SLF001
        assert panel.has_unsaved_changes() is True

        panel.apply_changes()
        assert fake.tz_offset == 3.0
        assert panel.has_unsaved_changes() is False


# ── merger ────────────────────────────────────────────────────────────


@pytest.mark.gui
class TestMergerTemplate:
    def test_exports_three_factories(self):
        assert callable(merger_template.make_home_card)
        assert callable(merger_template.make_settings_panel)
        assert callable(merger_template.make_runtime_panel)

    def test_settings_panel_apply_writes_gap_sec(self, qtbot):
        fake = _FakeMerger()
        panel = merger_template.make_settings_panel(
            parent=None, module=fake, state=None, params={}
        )
        qtbot.addWidget(panel)

        assert isinstance(panel, SettingsPanelProtocol)
        assert panel.validate() == []
        panel._gap_spin.setValue(2.5)  # noqa: SLF001
        assert panel.has_unsaved_changes() is True

        panel.apply_changes()
        assert fake.gap_sec == 2.5
        assert panel.has_unsaved_changes() is False


# ── renderer ──────────────────────────────────────────────────────────


@pytest.mark.gui
class TestRendererTemplate:
    def test_exports_three_factories(self):
        assert callable(renderer_template.make_home_card)
        assert callable(renderer_template.make_settings_panel)
        assert callable(renderer_template.make_runtime_panel)

    def test_settings_panel_is_readonly(self, qtbot):
        panel = renderer_template.make_settings_panel(
            parent=None,
            module=_FakeRenderer(),
            state=None,
            params={"filename": "merged.txt"},
        )
        qtbot.addWidget(panel)

        assert isinstance(panel, SettingsPanelProtocol)
        assert panel.validate() == []
        assert panel.has_unsaved_changes() is False
        # apply_changes is a no-op but must not raise
        panel.apply_changes()
        assert panel.has_unsaved_changes() is False
