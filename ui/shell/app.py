"""PySide6 entry point for Session Transcriber.

This is the main host for the Qt migration (ADR-017). By Phase 6 it
wires the :class:`SessionScreen` central widget to a real
:class:`RunController` that launches ``core.pipeline.run`` in a
background thread and streams stage progress back to the screen.

Phase 9 will replace the hardcoded fixture with a folder picker
selecting a real ``session_dir``. Until then, the ``Run`` button
surfaces a warning if no session has been loaded.

Run:
    python -m ui.shell.app
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from core.pipeline import PipelineParams
from ui.shell import theme
from ui.shell._demo_stub_panel import DemoStubPanel
from ui.shell.run_controller import RunController, RunRequest
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

        #: Current session folder. ``None`` until Phase 9 folder picker
        #: lands; ``_on_run_clicked`` warns and bails if unset.
        self._session_dir: Path | None = None

        self._session_screen = SessionScreen(_build_demo_session_data(), parent=self)
        self.setCentralWidget(self._session_screen)

        # SettingsDrawer — overlay, parent=self, НЕ в layout.
        self._settings_drawer = SettingsDrawer(self)

        # Run controller (QThread worker for core.pipeline.run)
        self._run_controller = RunController(parent=self)
        self._run_controller.started.connect(self._on_run_started)
        self._run_controller.stage.connect(self._on_run_stage)
        self._run_controller.finished.connect(self._on_run_finished)
        self._run_controller.failed.connect(self._on_run_failed)

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
        """Kick off pipeline run via :class:`RunController`.

        Phase 6: controller wired, but ``_session_dir`` is only set by
        Phase 9's folder picker. Until then, we show a friendly warning
        instead of exploding the user's screen.
        """
        if self._run_controller.is_running:
            _log.info("Run clicked while already running — ignored")
            return
        if self._session_dir is None:
            QMessageBox.information(
                self,
                "Нет сессии",
                "Сначала откройте папку сессии. "
                "Диалог выбора появится в Phase 9.",
            )
            return

        params = PipelineParams(
            speech_backend="gigaam",
            merger="script",
            renderer="plain-text",
            output_filename="merged.txt",
        )
        request = RunRequest(session_dir=self._session_dir, params=params)
        self._session_screen.set_state_running()
        started = self._run_controller.start(request)
        if not started:
            self._session_screen.set_state_idle()

    # ── Run controller slots ─────────────────────────────────────────

    def _on_run_started(self) -> None:
        _log.info("Pipeline run started on %s", self._session_dir)

    def _on_run_stage(self, stage: str, message: str) -> None:
        _log.info("Pipeline stage: %s (%s)", stage, message)
        self._session_screen.update_stage(stage, message)

    def _on_run_finished(self, output_path: str) -> None:
        _log.info("Pipeline finished: %s", output_path)
        self._session_screen.set_state_done(output_path)

    def _on_run_failed(self, error_text: str) -> None:
        _log.error("Pipeline failed: %s", error_text)
        self._session_screen.set_state_failed(error_text)

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
