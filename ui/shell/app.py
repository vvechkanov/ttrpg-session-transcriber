"""PySide6 entry point for Session Transcriber.

By Phase 9 this is the user-facing host for the whole application:
a folder picker populates :class:`SessionScreen` with real per-session
data, settings drawers resolve real templates through
:func:`core.ui_registry.resolve_template`, and the Run button kicks
off ``core.pipeline.run`` on a background :class:`RunController`
thread with live stage progress.

Run:
    python -m ui.shell.app
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from core.backend_installers import BackendId
from core.discovery import find_fvtt_chat_log
from core.pipeline import PipelineParams
from core.ui_registry import resolve_template
from sources import SPEECH_SOURCES
from sources.game_log.fvtt_chat import FvttChatSource
from ui.shell import theme
from ui.shell._demo_stub_panel import DemoStubPanel
from ui.shell.install_wizard import ensure_backend_installed
from ui.shell.run_controller import RunController, RunRequest
from ui.shell.screens import ModelsScreen, SessionScreen, SessionScreenData
from ui.shell.settings_drawer import SettingsDrawer
from ui.widgets import SourceCardData

#: Maps ``PipelineParams.speech_backend`` values to the
#: :class:`core.backend_installers.BackendId` that must be installed
#: before the pipeline can run with that backend. Kept here (UI layer)
#: rather than in ``core/`` because the mapping is a UI concern: it
#: decides which install wizard to show to the user, nothing more.
_BACKEND_FOR_SPEECH: dict[str, BackendId] = {
    "gigaam": BackendId.GIGAAM_RNNT_FP32,
    "faster-whisper": BackendId.FASTER_WHISPER_LARGE_V3_RU,
}

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


_AUDIO_EXTENSIONS: tuple[str, ...] = (".flac", ".wav", ".mp3", ".ogg", ".m4a", ".opus")


def _empty_session_data() -> SessionScreenData:
    """Placeholder shown before the user opens a folder."""
    return SessionScreenData(
        project_name="Нет сессии",
        session_name="Откройте папку через меню «Файл → Открыть…»",
        sources=(),
    )


def _scan_audio_files(session_dir: Path) -> tuple[str, ...]:
    """Port of the same helper in ``audio_source_template``.

    Local copy to keep ``app.py`` independent of the audio template's
    private helpers; both implementations stay trivial.
    """
    files: list[str] = []
    for p in sorted(session_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in _AUDIO_EXTENSIONS:
            continue
        if p.stem.lower().startswith("craig"):
            continue
        files.append(p.name)
    return tuple(files)


def _build_session_from_dir(session_dir: Path) -> tuple[
    SessionScreenData,
    "list[object]",
]:
    """Construct screen data + list of pipeline modules for a real session.

    The module list parallels ``SessionScreenData.sources`` — index N of
    the screen cards maps to index N of modules, so
    ``source_configure_requested(index)`` can pick up the right module
    instance to feed the settings template.
    """
    audio_files = _scan_audio_files(session_dir)

    # Default speech backend — GigaAMSource. Users can change it in the
    # drawer (precision/device/variant) after opening it.
    gigaam_cls = SPEECH_SOURCES["gigaam"]
    try:
        gigaam_module = gigaam_cls()
    except Exception:  # pragma: no cover — constructor should be light
        _log.exception("Failed to build GigaAMSource; using stub")
        gigaam_module = gigaam_cls  # type: ignore[assignment]

    sources: list[SourceCardData] = [
        SourceCardData(
            title="Аудио",
            subtitle="GigaAM-v3 RNNT · русский",
            files=audio_files,
            status="ready" if audio_files else "warning",
            status_text="готов" if audio_files else "нет файлов",
        )
    ]
    modules: list[object] = [gigaam_module]

    chat_log = find_fvtt_chat_log(session_dir)
    if chat_log is not None:
        try:
            line_count = chat_log.read_text(encoding="utf-8", errors="ignore").count("\n")
        except OSError:
            line_count = 0
        chat_module = FvttChatSource(chat_log_path=chat_log)
        sources.append(
            SourceCardData(
                title="Foundry VTT чат",
                subtitle="fvtt-chat parser",
                files=(chat_log.name,),
                files_hint=f"{line_count} строк",
                status="ready",
                status_text="готов",
            )
        )
        modules.append(chat_module)

    data = SessionScreenData(
        project_name=session_dir.parent.name or session_dir.name,
        session_name=session_dir.name,
        sources=tuple(sources),
    )
    return data, modules


class MainWindow(QMainWindow):
    """Session Transcriber main window (Phase 9).

    Responsibilities:
        * folder picker (``File → Open session…``) sets the current
          ``session_dir`` and rebuilds :class:`SessionScreen` from real
          pipeline modules (:mod:`sources` / :mod:`mergers` /
          :mod:`renderers`);
        * forwards source/merger/output configure clicks to
          :func:`core.ui_registry.resolve_template` and opens the
          matching ``make_settings_panel`` inside
          :class:`SettingsDrawer`;
        * runs :func:`core.pipeline.run` on a background
          :class:`RunController` thread and routes stage progress back
          to the screen.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(_WINDOW_TITLE)
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self.setStyleSheet(
            f"QMainWindow {{ background-color: {theme.COLOR_BACKGROUND}; }}"
        )

        #: Current session folder. ``None`` until the user opens one.
        self._session_dir: Path | None = None
        #: Pipeline modules parallel to ``_session_screen._data.sources``.
        self._source_modules: list[object] = []
        #: Merger + renderer module instances — single-instance in MVP.
        self._merger_module = self._default_merger()
        self._renderer_module = self._default_renderer()

        self._session_screen = SessionScreen(_empty_session_data(), parent=self)
        self.setCentralWidget(self._session_screen)

        # SettingsDrawer — overlay, parent=self, НЕ в layout.
        self._settings_drawer = SettingsDrawer(self)

        # Run controller (QThread worker for core.pipeline.run)
        self._run_controller = RunController(parent=self)
        self._run_controller.started.connect(self._on_run_started)
        self._run_controller.stage.connect(self._on_run_stage)
        self._run_controller.finished.connect(self._on_run_finished)
        self._run_controller.failed.connect(self._on_run_failed)

        self._build_menu_bar()

        # ── Signal wiring ─────────────────────────────────────────
        self._wire_session_screen_signals()

    # ── Menu bar ─────────────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&Файл")

        open_action = QAction("Открыть сессию…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_session)
        file_menu.addAction(open_action)

        file_menu.addSeparator()
        quit_action = QAction("Выход", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # "Модели" top-level menu — available both before and after a
        # session is loaded (managing backends is independent of the
        # current session folder).
        models_menu = menu.addMenu("&Модели")
        manage_models_action = QAction("Управление моделями…", self)
        manage_models_action.triggered.connect(self._on_manage_models)
        models_menu.addAction(manage_models_action)

    def _on_manage_models(self) -> None:
        """Open the modal "Управление моделями" dialog."""
        dialog = ModelsScreen(parent=self)
        dialog.exec()

    def _wire_session_screen_signals(self) -> None:
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

    # ── Session loading ─────────────────────────────────────────────

    def _on_open_session(self) -> None:
        """Prompt for a folder and rebuild the SessionScreen from it."""
        picked = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку сессии",
            str(self._session_dir) if self._session_dir else "",
        )
        if not picked:
            return
        self._load_session(Path(picked))

    def _load_session(self, session_dir: Path) -> None:
        if not session_dir.is_dir():
            QMessageBox.warning(
                self, "Папка не найдена", f"{session_dir} не существует."
            )
            return

        try:
            data, modules = _build_session_from_dir(session_dir)
        except Exception as exc:  # noqa: BLE001 — UI boundary
            _log.exception("Failed to build session view")
            QMessageBox.critical(
                self,
                "Ошибка загрузки сессии",
                f"{session_dir}\n\n{exc}",
            )
            return

        self._session_dir = session_dir
        self._source_modules = modules
        self._replace_session_screen(data)

    def _replace_session_screen(self, data: SessionScreenData) -> None:
        """Swap the central widget for a fresh SessionScreen.

        PySide6 QMainWindow takes ownership of the new central widget
        and deletes the old one, so signal reconnection is mandatory.
        """
        new_screen = SessionScreen(data, parent=self)
        self.setCentralWidget(new_screen)
        self._session_screen = new_screen
        self._wire_session_screen_signals()

    # ── Settings drawer routing (Phase 9: real templates) ─────────

    def _on_source_configure(self, index: int) -> None:
        if not (0 <= index < len(self._source_modules)):
            self._open_demo_drawer(title="Настройки источника", subtitle="")
            return
        module = self._source_modules[index]
        card = self._session_screen._data.sources[index]  # noqa: SLF001
        self._open_module_drawer(
            module=module,
            title=f"Настройки · {card.title}",
            subtitle=card.subtitle,
        )

    def _on_merger_configure(self) -> None:
        self._open_module_drawer(
            module=self._merger_module,
            title="Настройки мержера",
            subtitle="script / timeline-v1",
        )

    def _on_output_configure(self) -> None:
        self._open_module_drawer(
            module=self._renderer_module,
            title="Настройки вывода",
            subtitle="plain-text / merged.txt",
        )

    def _on_add_source(self) -> None:
        QMessageBox.information(
            self,
            "Добавление источника",
            "Мульти-источник поддерживается через ui_config на классах "
            "модулей. Интерактивное добавление через GUI планируется "
            "позже.",
        )

    def _open_module_drawer(
        self, *, module: object, title: str, subtitle: str
    ) -> None:
        """Resolve the module's ui_config template and open its drawer."""
        ui_config = getattr(module, "ui_config", None)
        if ui_config is None:
            self._open_demo_drawer(title=title, subtitle=subtitle)
            return
        try:
            template = resolve_template(ui_config)
        except Exception:  # noqa: BLE001 — UI boundary
            _log.exception("Failed to resolve template for %r", module)
            self._open_demo_drawer(title=title, subtitle=subtitle)
            return

        state = self._build_state_for(module, template)
        try:
            panel = template.make_settings_panel(
                parent=None,
                module=module,
                state=state,
                params=ui_config.params,
            )
        except Exception:  # noqa: BLE001 — UI boundary
            _log.exception("make_settings_panel failed for %r", module)
            self._open_demo_drawer(title=title, subtitle=subtitle)
            return

        self._settings_drawer.open_with_panel(panel, title=title, subtitle=subtitle)

    def _build_state_for(self, module: object, template) -> object | None:
        """Construct the template's ``state`` dataclass with session_dir.

        Each template exposes a ``*State`` dataclass with a
        ``session_dir`` field. We look for the first such class in the
        template module and instantiate it. Returns ``None`` if nothing
        matches — templates accept that as "no state".
        """
        for attr in dir(template):
            if not attr.endswith("State"):
                continue
            candidate = getattr(template, attr)
            if not isinstance(candidate, type):
                continue
            try:
                return candidate(session_dir=self._session_dir)
            except TypeError:
                try:
                    return candidate()
                except TypeError:
                    continue
        return None

    # ── Run pipeline ─────────────────────────────────────────────────

    def _on_run_clicked(self) -> None:
        if self._run_controller.is_running:
            _log.info("Run clicked while already running — ignored")
            return
        if self._session_dir is None:
            QMessageBox.information(
                self,
                "Нет сессии",
                "Сначала откройте папку сессии через «Файл → Открыть…».",
            )
            return

        params = self._build_pipeline_params()

        # Pre-flight: make sure the ASR backend the pipeline is about
        # to call is actually installed. The installer EXE already
        # ticks the default backend, so this is only reached when the
        # user switched to a non-installed backend in the settings
        # drawer or manually deleted the backend directory.
        if not self._ensure_speech_backend_installed(params.speech_backend):
            return

        request = RunRequest(session_dir=self._session_dir, params=params)
        self._session_screen.set_state_running()
        started = self._run_controller.start(request)
        if not started:
            self._session_screen.set_state_idle()

    def _ensure_speech_backend_installed(self, speech_backend: str) -> bool:
        """Gate the Run button behind an Epic A tracked install check.

        Returns ``True`` if the backend is (now) installed and the
        run may proceed. Returns ``False`` if the user cancelled the
        install or it failed — in which case the caller aborts.
        """
        backend_id = _BACKEND_FOR_SPEECH.get(speech_backend)
        if backend_id is None:
            # Unknown / unmapped backend — let the pipeline handle it
            # and surface the error itself. Nothing to install.
            return True

        try:
            installed = ensure_backend_installed(backend_id, parent=self)
        except Exception as exc:  # noqa: BLE001 — UI boundary
            _log.exception("Install wizard failed for %s", backend_id)
            QMessageBox.critical(
                self,
                "Ошибка установки модели",
                f"Не удалось установить {backend_id.value}:\n\n{exc}",
            )
            return False

        if not installed:
            QMessageBox.information(
                self,
                "Установка отменена",
                f"Запуск отменён — модель {backend_id.value} не установлена.",
            )
            return False
        return True

    def _build_pipeline_params(self) -> PipelineParams:
        """Build PipelineParams from the current modules' user-visible state.

        GigaAMSource exposes ``variant / precision / device /
        num_threads``. We mirror them into PipelineParams. The CLI /
        legacy path always used the dataclass defaults; users who
        tweaked the drawer get their changes applied here.
        """
        speech_module = None
        for m in self._source_modules:
            name = getattr(m, "name", None)
            if name == "gigaam":
                speech_module = m
                break
        if speech_module is not None:
            variant = getattr(speech_module, "variant", "rnnt")
            precision = getattr(speech_module, "precision", "fp32")
            return PipelineParams(
                speech_backend="gigaam",
                gigaam_variant=getattr(variant, "value", variant),
                gigaam_precision=getattr(precision, "value", precision),
                device=getattr(speech_module, "device", "cpu"),
                num_threads=getattr(speech_module, "num_threads", 4),
                merger="script",
                renderer="plain-text",
                output_filename="merged.txt",
            )
        return PipelineParams(
            speech_backend="gigaam",
            merger="script",
            renderer="plain-text",
            output_filename="merged.txt",
            device="cpu",
        )

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
            panel, title=title, subtitle=subtitle or "—"
        )

    # ── Defaults for merger / renderer ───────────────────────────────

    @staticmethod
    def _default_merger() -> object:
        from mergers import MERGERS
        cls = MERGERS["script"]
        try:
            return cls()
        except Exception:  # pragma: no cover
            return cls  # type: ignore[return-value]

    @staticmethod
    def _default_renderer() -> object:
        from renderers import RENDERERS
        cls = RENDERERS["plain-text"]
        try:
            return cls()
        except Exception:  # pragma: no cover
            return cls  # type: ignore[return-value]


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
