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
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

# Figma v1 theme tokens (see docs/design/mockups/figma-make/.../styles/theme.css).
_BG_COLOR = "#FAF8F5"
_MUTED_FG = "#6B625A"

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

        label = QLabel(_PLACEHOLDER_TEXT, central)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {_MUTED_FG}; font-size: 16px;")
        layout.addWidget(label)

        self.setCentralWidget(central)


def main() -> int:
    """Boot the Qt application and return its exit code."""
    app = QApplication(sys.argv)
    app.setFont(_pick_ui_font())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
