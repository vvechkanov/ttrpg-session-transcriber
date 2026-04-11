"""Minimal PySide6 entry point for Session Transcriber.

This is infrastructure scaffolding for the Qt migration (ADR-017).
Phase 3 of the migration plan lands the real Session Detail screen
as the central widget — still with fictional data, still no pipeline.
Signals from :class:`SessionScreen` are wired up to log messages and
open the demo SettingsDrawer; real handlers arrive in Phase 4+.

Run:
    python -m ui.shell.app

Do NOT add pipeline business logic here. Background threads, real
modules and the actual run button belong to Phase 5-6 and will live
in their own modules under ``ui/shell/`` (``run_controller.py`` et al).
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMainWindow

from ui.shell import theme
from ui.shell._demo_stub_panel import DemoStubPanel
from ui.shell.screens import SessionScreen, SessionScreenData
from ui.shell.settings_drawer import SettingsDrawer
from ui.widgets import SourceCardData

_WINDOW_TITLE = "Session Transcriber — диктофон сессий"
_DEFAULT_WIDTH = 1400
_DEFAULT_HEIGHT = 900

_log = logging.getLogger(__name__)


def _pick_ui_font() -> QFont:
    """Return Inter if the system has it installed, else the platform default.

    The Figma mockups use Inter; if it is not on the host we must not crash —
    Qt's default sans-serif is an acceptable fallback for the skeleton phase.
    """
    families = set(QFontDatabase.families())
    if "Inter" in families:
        return QFont("Inter", 11)
    return QFont()


def _build_demo_session_data() -> SessionScreenData:
    """Фикстура Session Detail для Phase 3.

    Эти данные — чистая презентация. В Phase 5+ хост начнёт собирать
    ``SessionScreenData`` из реального списка модулей pipeline через
    template registry. До тех пор здесь жёстко зашитый сценарий
    «Storm King's Thunder / Сессия 14» — тот же, что в Figma v1.
    """
    return SessionScreenData(
        project_name="Storm King's Thunder",
        session_name="Сессия 14 — Битва на мосту",
        sources=(
            SourceCardData(
                title="Аудио",
                subtitle="GigaAM-v3 RNNT · русский",
                files=(
                    "1-Andrey.flac",
                    "2-Boris.flac",
                    "3-Carol.flac",
                    "4-Dmitry.flac",
                    "5-Eve.flac",
                    "6-Frank.flac",
                ),
                status="ready",
                status_text="готов",
            ),
            SourceCardData(
                title="Foundry VTT чат",
                subtitle="",
                files=("chat-log-2026-04-10.db",),
                files_hint="1423 реплики · 12 участников",
                status="ready",
                status_text="готов",
            ),
        ),
    )


class MainWindow(QMainWindow):
    """Session Transcriber main window.

    Central widget — :class:`SessionScreen` (Screen 3 / Session Detail).
    Phase 3: только idle state, фикстура, нет реального pipeline.

    SettingsDrawer создаётся один раз и переиспользуется. На клик по
    любой кнопке ``[Настроить]`` хост открывает demo-заглушку; в Phase
    4+ этот слот начнёт резолвить реальный темплейт модуля через
    ``core.ui_registry.resolve_template``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(_WINDOW_TITLE)
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self.setStyleSheet(
            f"QMainWindow {{ background-color: {theme.COLOR_BACKGROUND}; }}"
        )

        self._session_screen = SessionScreen(_build_demo_session_data(), parent=self)
        self.setCentralWidget(self._session_screen)

        # SettingsDrawer — overlay, parent=self, НЕ в layout.
        self._settings_drawer = SettingsDrawer(self)

        # ── Signal wiring ─────────────────────────────────────────
        self._session_screen.source_configure_requested.connect(
            self._on_source_configure
        )
        self._session_screen.merger_configure_requested.connect(
            self._on_merger_configure
        )
        self._session_screen.output_configure_requested.connect(
            self._on_output_configure
        )
        self._session_screen.add_source_requested.connect(self._on_add_source)
        self._session_screen.run_clicked.connect(self._on_run_clicked)

    # ── Slots: Phase 3 stubs ─────────────────────────────────────────

    def _on_source_configure(self, index: int) -> None:
        """Temporary: открывает demo drawer. Phase 4+ → real template."""
        data = self._session_screen._data  # noqa: SLF001 — короткий путь до Phase 4
        if 0 <= index < len(data.sources):
            card = data.sources[index]
            self._open_demo_drawer(
                title=f"Настройки · {card.title}",
                subtitle=card.subtitle,
            )

    def _on_merger_configure(self) -> None:
        self._open_demo_drawer(
            title="Настройки мержера",
            subtitle="timeline-v1",
        )

    def _on_output_configure(self) -> None:
        self._open_demo_drawer(
            title="Настройки вывода",
            subtitle="merged.txt",
        )

    def _on_add_source(self) -> None:
        _log.info("[Phase 3 stub] Add source requested")

    def _on_run_clicked(self) -> None:
        _log.info("[Phase 3 stub] Run clicked — real pipeline arrives in Phase 6")

    def _open_demo_drawer(self, *, title: str, subtitle: str) -> None:
        panel = DemoStubPanel()
        self._settings_drawer.open_with_panel(
            panel,
            title=title,
            subtitle=subtitle or "demo stub (заменится в Phase 4)",
        )


def main() -> int:
    """Boot the Qt application and return its exit code."""
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setFont(_pick_ui_font())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
