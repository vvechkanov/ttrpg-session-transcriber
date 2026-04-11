"""Minimal PySide6 entry point for Session Transcriber.

This is infrastructure scaffolding for the Qt migration (ADR-017). The
real UI will be built up in later phases; for now this module only proves
that PySide6 boots, displays a window with the project theme background
color, and exits cleanly.

Run:
    python -m ui.shell.app

Do NOT add business logic, signals, threads, menus, or status bars here.
Those belong to later phases and will have their own modules under
`ui/shell/`.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.shell._demo_stub_panel import DemoStubPanel
from ui.shell.settings_drawer import SettingsDrawer

# Figma v1 theme tokens (see docs/design/mockups/figma-make/.../styles/theme.css).
_BG_COLOR = "#FAF8F5"
_MUTED_FG = "#6B625A"
_FG_COLOR = "#2D2520"
_ACCENT = "#D4843B"

_WINDOW_TITLE = "Session Transcriber — диктофон сессий"
_PLACEHOLDER_TEXT = "Qt skeleton. Реальный UI появится по фазам ADR-017."

_DEFAULT_WIDTH = 1400
_DEFAULT_HEIGHT = 900


def _pick_ui_font() -> QFont:
    """Return Inter if the system has it installed, else the platform default.

    The Figma mockups use Inter; if it is not on the host we must not crash —
    Qt's default sans-serif is an acceptable fallback for the skeleton phase.
    """
    families = set(QFontDatabase.families())
    if "Inter" in families:
        return QFont("Inter", 11)
    return QFont()


class MainWindow(QMainWindow):
    """Empty main window — placeholder shell for the Qt migration."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(_WINDOW_TITLE)
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self.setStyleSheet(f"QMainWindow {{ background-color: {_BG_COLOR}; }}")

        central = QWidget(self)
        central.setStyleSheet(f"background-color: {_BG_COLOR};")
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        label = QLabel(_PLACEHOLDER_TEXT, central)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {_MUTED_FG}; font-size: 16px;")
        layout.addWidget(label)

        # Manual-test button for SettingsDrawer (Phase 2). Удаляется в Phase 3
        # когда появится реальный Session Detail экран с карточками модулей.
        demo_button = QPushButton("Показать SettingsDrawer (demo)", central)
        demo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        demo_button.setStyleSheet(
            f"""
            QPushButton {{
                color: {_ACCENT};
                background: transparent;
                border: 1px solid {_ACCENT};
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {_ACCENT};
                color: white;
            }}
            """
        )
        demo_button.clicked.connect(self._on_show_demo_drawer)
        layout.addWidget(demo_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.setCentralWidget(central)

        # SettingsDrawer — создаётся один раз, переиспользуется. Parent=self,
        # но не в layout — overlay pattern.
        self._settings_drawer = SettingsDrawer(self)

    def _on_show_demo_drawer(self) -> None:
        """Слот для кнопки «Показать SettingsDrawer (demo)»."""
        panel = DemoStubPanel()
        self._settings_drawer.open_with_panel(
            panel,
            title="Настройки · Аудио",
            subtitle="GigaAM-v3 RNNT · русский (demo stub)",
        )


def main() -> int:
    """Boot the Qt application and return its exit code."""
    app = QApplication(sys.argv)
    app.setFont(_pick_ui_font())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
