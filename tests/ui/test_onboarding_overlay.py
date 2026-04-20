"""Tests for :class:`ui.shell.screens.OnboardingOverlay` (P2b).

Covers:
    * The welcome card renders with title, body, and dismiss button.
    * Clicking the dismiss button calls
      :func:`core.onboarding_state.mark_onboarded` and hides the
      overlay.
    * The overlay resizes with its parent.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from ui.shell.screens import OnboardingOverlay
from ui.shell.screens import onboarding_overlay as overlay_module


@pytest.mark.gui
class TestOnboardingOverlay:
    def test_card_renders_with_welcome_copy(self, qtbot):
        parent = QWidget()
        parent.resize(800, 600)
        qtbot.addWidget(parent)
        overlay = OnboardingOverlay(parent=parent)
        parent.show()
        qtbot.waitExposed(parent)

        labels = overlay.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert any("Добро пожаловать" in t for t in texts)
        assert any("перетащите" in t.lower() for t in texts)

        dismiss_buttons = [
            b for b in overlay.findChildren(QPushButton)
            if "Понятно" in b.text()
        ]
        assert len(dismiss_buttons) == 1

    def test_dismiss_calls_mark_onboarded_and_hides(self, qtbot, monkeypatch):
        parent = QWidget()
        parent.resize(800, 600)
        qtbot.addWidget(parent)
        overlay = OnboardingOverlay(parent=parent)
        parent.show()
        qtbot.waitExposed(parent)
        overlay.show()

        calls: list[bool] = []
        # The overlay imports ``core.onboarding_state`` lazily inside
        # its click slot, so patching the attribute on the real module
        # is what the slot actually resolves.
        from core import onboarding_state as os_module

        monkeypatch.setattr(
            os_module, "mark_onboarded", lambda: calls.append(True)
        )

        dismiss_button = [
            b for b in overlay.findChildren(QPushButton)
            if "Понятно" in b.text()
        ][0]

        with qtbot.waitSignal(overlay.dismissed, timeout=1000):
            dismiss_button.click()

        assert calls == [True]
        assert overlay.isHidden() is True

    def test_overlay_covers_full_parent_after_resize(self, qtbot):
        parent = QWidget()
        parent.resize(400, 300)
        qtbot.addWidget(parent)
        overlay = OnboardingOverlay(parent=parent)
        parent.show()
        qtbot.waitExposed(parent)

        # Initial cover
        assert overlay.geometry().width() == parent.width()
        assert overlay.geometry().height() == parent.height()

        # Resize parent and confirm the overlay follows.
        parent.resize(QSize(1000, 800))
        # Qt may defer the resize event; process events to flush it.
        qtbot.wait(50)

        assert overlay.geometry().width() == parent.width()
        assert overlay.geometry().height() == parent.height()

    def test_module_exposes_overlay_class(self):
        # Guard against accidental renames — the screens package
        # exports ``OnboardingOverlay`` and the submodule lives at the
        # expected dotted path.
        assert overlay_module.OnboardingOverlay is OnboardingOverlay
