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

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontDatabase,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from core import onboarding_state, recent_sessions
from core.backend_installers import BackendId
from core.discovery import find_fvtt_chat_log
from core.pipeline import PipelineParams
from core.ui_registry import resolve_template
from sources import SPEECH_SOURCES
from sources.game_log.fvtt_chat import FvttChatSource
from ui.shell import theme
from ui.shell._demo_stub_panel import DemoStubPanel
from ui.shell.add_source_dialog import (
    KEY_FASTER_WHISPER,
    KEY_FVTT_CHAT,
    KEY_GIGAAM,
    AddSourceDialog,
)
from ui.shell.install_wizard import ensure_backend_installed
from ui.shell.run_controller import RunController, RunRequest
from ui.shell.screens import (
    EmptyStateScreen,
    ModelsScreen,
    OnboardingOverlay,
    SessionScreen,
    SessionScreenData,
)
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

#: Maps :class:`ui.shell.add_source_dialog.ParserOption` keys to the
#: matching :class:`BackendId`. Chat parsers don't need a model and so
#: don't appear here. Used by :meth:`MainWindow._on_add_source` to
#: gate the new source behind an install wizard when necessary.
_BACKEND_FOR_PARSER_KEY: dict[str, BackendId] = {
    KEY_GIGAAM: BackendId.GIGAAM_RNNT_FP32,
    KEY_FASTER_WHISPER: BackendId.FASTER_WHISPER_LARGE_V3_RU,
}

_WINDOW_TITLE = "Session Transcriber — диктофон сессий"
_DEFAULT_WIDTH = 1400
# 960 clears the full 4-block stack with ~1 px to spare on a 1080p screen
# (title bar + taskbar ≈ 120 px). Below that the content starts scrolling,
# which is fine — just means the user shrank the window on purpose.
_DEFAULT_HEIGHT = 960

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


def _drop_payload_single_dir(mime: QMimeData) -> Path | None:
    """Return the dropped path iff it's a single existing directory.

    Used by :meth:`MainWindow.dragEnterEvent` / :meth:`dropEvent` to
    decide whether a window-level drop should route to
    ``_load_session``. Returns ``None`` silently for anything else —
    per P1a the window does not surface a warning; the empty-state
    drop zone handles that case on its own.
    """
    if not mime.hasUrls():
        return None
    urls = mime.urls()
    if len(urls) != 1:
        return None
    path_str = urls[0].toLocalFile()
    if not path_str:
        return None
    path = Path(path_str)
    if not path.is_dir():
        return None
    return path


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
        # Guard rails: below this the 4-block card layout starts clipping
        # (cards wrap onto 2 rows but block 3's hero card still needs
        # ~600 px to breathe). Users can still scroll if they insist.
        self.setMinimumSize(900, 640)
        self.setStyleSheet(
            f"QMainWindow {{ background-color: {theme.COLOR_BACKGROUND}; }}"
        )

        # P1a — accept folder drops anywhere on the window, so the user
        # doesn't have to aim at the empty-state drop zone. Once a
        # session is loaded the dropped folder still routes through
        # ``_load_session``, replacing the current session.
        self.setAcceptDrops(True)

        #: Current session folder. ``None`` until the user opens one.
        self._session_dir: Path | None = None
        #: Pipeline modules parallel to ``_session_screen._data.sources``.
        self._source_modules: list[object] = []
        #: Merger + renderer module instances — single-instance in MVP.
        self._merger_module = self._default_merger()
        self._renderer_module = self._default_renderer()

        # P0a — start on the empty state screen. A full SessionScreen
        # is built lazily inside :meth:`_load_session`, so users only
        # see the 4-block layout once they actually have a session.
        # P2a — seed the screen with the persisted recent-sessions list
        # so returning users see their previous sessions on launch.
        initial_recent = recent_sessions.load_recent()
        self._session_screen: SessionScreen | None = None
        self._empty_state_screen: EmptyStateScreen | None = EmptyStateScreen(
            parent=self, recent=initial_recent
        )
        self._empty_state_screen.pick_folder_requested.connect(
            self._on_open_session
        )
        self._empty_state_screen.folder_dropped.connect(self._load_session)
        self._empty_state_screen.recent_session_selected.connect(
            self._load_session
        )
        self.setCentralWidget(self._empty_state_screen)

        # P2b — first-run onboarding overlay. Only show it when the
        # user has never dismissed it AND has no recents — if they do
        # have recents, they've obviously opened a session before, so
        # the welcome would be redundant (they may have manually wiped
        # the flag file).
        self._onboarding_overlay: OnboardingOverlay | None = None
        if onboarding_state.is_first_run() and not initial_recent:
            self._onboarding_overlay = OnboardingOverlay(parent=self)
            self._onboarding_overlay.dismissed.connect(
                self._on_onboarding_dismissed
            )
            self._onboarding_overlay.show()
            self._onboarding_overlay.raise_()

        # SettingsDrawer — overlay, parent=self, НЕ в layout.
        self._settings_drawer = SettingsDrawer(self)

        # Run controller (QThread worker for core.pipeline.run)
        self._run_controller = RunController(parent=self)
        self._run_controller.started.connect(self._on_run_started)
        self._run_controller.stage.connect(self._on_run_stage)
        self._run_controller.finished.connect(self._on_run_finished)
        self._run_controller.failed.connect(self._on_run_failed)

        self._build_menu_bar()

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
        assert self._session_screen is not None, (
            "_wire_session_screen_signals called before SessionScreen exists"
        )
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

    # ── Window-level drag and drop (P1a) ────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """Accept the drag when the payload is a single directory.

        Anything else (a file, multiple items) is silently ignored —
        :class:`EmptyStateScreen` handles the single-file case with a
        user-visible warning when the drop lands on it directly. We
        don't duplicate that here because it would fire twice when the
        child accepts the event.
        """
        if _drop_payload_single_dir(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path = _drop_payload_single_dir(event.mimeData())
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self._load_session(path)

    def handle_mime_drop(self, mime: QMimeData) -> None:
        """Testable entry point for mime-data-driven drops.

        PySide6 cannot round-trip a Python-built :class:`QDropEvent`
        through the C++ layer without the ``mimeData()`` getter losing
        the concrete :class:`QMimeData` type. Tests call this helper
        with a plain :class:`QMimeData` to exercise the drop logic
        without synthesising a real event.
        """
        path = _drop_payload_single_dir(mime)
        if path is None:
            return
        self._load_session(path)

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

        # P2a — persist for the next launch. Failures here are logged
        # but not surfaced: the session has already loaded successfully
        # and a disk error on the config dir must not break the UX.
        try:
            recent_sessions.add_recent(session_dir)
        except Exception:  # noqa: BLE001 — best-effort persistence
            _log.exception("Failed to persist recent session %s", session_dir)

    def _replace_session_screen(self, data: SessionScreenData) -> None:
        """Swap the central widget for a fresh SessionScreen.

        PySide6 QMainWindow takes ownership of the new central widget
        and deletes the old one, so signal reconnection is mandatory.
        The run button is gated on having at least one source card (P0b).
        """
        new_screen = SessionScreen(data, parent=self)
        self.setCentralWidget(new_screen)
        # setCentralWidget takes ownership and deletes the old central
        # widget; clear our reference so nothing reads a dangling
        # EmptyStateScreen after the swap.
        self._empty_state_screen = None
        self._session_screen = new_screen
        self._wire_session_screen_signals()
        new_screen.set_run_enabled(len(data.sources) > 0)

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
        """Open the parser picker; install the backing model if needed.

        Flow:
            1. ``AddSourceDialog`` — user picks a parser type (speech
               or chat).
            2. If the picked parser has an ASR backend and that backend
               is not installed, confirm with the user and then run
               :func:`ui.shell.install_wizard.ensure_backend_installed`.
               The chat parser has no model dependency and skips this
               step entirely.
            3. On success, build the module and append a card to the
               session screen so the user sees the new source in
               block 1 immediately.
        """
        dialog = AddSourceDialog(parent=self)
        if dialog.exec() != QDialog.Accepted or dialog.selected_key is None:
            return
        key = dialog.selected_key

        backend_id = _BACKEND_FOR_PARSER_KEY.get(key)
        if backend_id is not None and not self._confirm_and_install_backend(
            backend_id
        ):
            return

        new_module = self._build_module_for_key(key)
        if new_module is None:
            return
        card = self._build_card_for_module(key, new_module)
        self._append_source(new_module, card)

    def _confirm_and_install_backend(self, backend_id: BackendId) -> bool:
        """Ask the user before a multi-GB download, then run the wizard.

        Returns ``True`` when the backend is installed (either because
        it already was or because the user accepted the prompt and the
        wizard succeeded). Returns ``False`` when the user cancelled or
        the install failed — in which case no card is added.
        """
        from core.backend_installers import BACKENDS, is_backend_installed

        if is_backend_installed(backend_id):
            return True

        info = BACKENDS[backend_id]
        size_mb = info.approx_download_bytes // 1_000_000
        confirm = QMessageBox.question(
            self,
            "Установить модель?",
            (
                f"Для этого парсера нужна модель:\n\n"
                f"{info.title}\n"
                f"Размер загрузки: ~{size_mb} MB\n\n"
                "Установить сейчас?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return False

        try:
            return ensure_backend_installed(backend_id, parent=self)
        except Exception as exc:  # noqa: BLE001 — UI boundary
            _log.exception("Install wizard failed for %s", backend_id)
            QMessageBox.critical(
                self,
                "Ошибка установки модели",
                f"Не удалось установить {backend_id.value}:\n\n{exc}",
            )
            return False

    def _build_module_for_key(self, key: str) -> object | None:
        """Construct a pipeline module instance for the picked parser.

        Returns ``None`` (with a user-visible warning) when the key is
        unknown or the module's constructor raises — this keeps the
        session screen in a consistent state instead of appending a
        half-built card.
        """
        try:
            if key == KEY_GIGAAM:
                return SPEECH_SOURCES["gigaam"]()
            if key == KEY_FASTER_WHISPER:
                return SPEECH_SOURCES["faster-whisper"]()
            if key == KEY_FVTT_CHAT:
                chat_log = (
                    find_fvtt_chat_log(self._session_dir)
                    if self._session_dir is not None
                    else None
                )
                if chat_log is None:
                    QMessageBox.warning(
                        self,
                        "Чат-лог не найден",
                        (
                            "В выбранной папке сессии нет файла "
                            "foundry-чата. Добавьте файл и повторите."
                        ),
                    )
                    return None
                return FvttChatSource(chat_log_path=chat_log)
        except Exception as exc:  # noqa: BLE001 — UI boundary
            _log.exception("Failed to construct module for key=%r", key)
            QMessageBox.critical(
                self,
                "Ошибка добавления парсера",
                f"Не удалось создать парсер {key!r}: {exc}",
            )
            return None
        QMessageBox.warning(
            self,
            "Неизвестный парсер",
            f"Ключ парсера {key!r} не поддерживается.",
        )
        return None

    def _build_card_for_module(self, key: str, module: object) -> SourceCardData:
        """Build a ready-to-insert :class:`SourceCardData` for ``module``.

        The card reflects whatever files are currently on disk under
        ``self._session_dir`` (audio scan for speech parsers, chat log
        line count for the chat parser). If no session is open yet the
        card falls back to ``"нет файлов"`` status so the user still
        sees their pick in the list.
        """
        if key in (KEY_GIGAAM, KEY_FASTER_WHISPER):
            audio_files = (
                _scan_audio_files(self._session_dir)
                if self._session_dir is not None
                else ()
            )
            if key == KEY_GIGAAM:
                title, subtitle = "Аудио", "GigaAM-v3 RNNT · русский"
            else:
                title, subtitle = (
                    "Аудио",
                    "faster-whisper large-v3 · русский",
                )
            return SourceCardData(
                title=title,
                subtitle=subtitle,
                files=audio_files,
                status="ready" if audio_files else "warning",
                status_text="готов" if audio_files else "нет файлов",
            )
        if key == KEY_FVTT_CHAT:
            chat_log = getattr(module, "chat_log_path", None)
            files: tuple[str, ...] = ()
            files_hint = ""
            if chat_log is not None:
                files = (chat_log.name,)
                try:
                    line_count = chat_log.read_text(
                        encoding="utf-8", errors="ignore"
                    ).count("\n")
                    files_hint = f"{line_count} строк"
                except OSError:
                    files_hint = ""
            return SourceCardData(
                title="Foundry VTT чат",
                subtitle="fvtt-chat parser",
                files=files,
                files_hint=files_hint,
                status="ready",
                status_text="готов",
            )
        return SourceCardData(
            title=key,
            subtitle="",
            files=(),
            status="warning",
            status_text="unknown",
        )

    def _append_source(
        self, module: object, card: SourceCardData
    ) -> None:
        """Append a new source to the session and rebuild the screen.

        ``SessionScreenData`` is a frozen dataclass, so we construct a
        fresh instance with the extra card rather than mutating the
        existing one. The central widget is swapped atomically via
        :meth:`_replace_session_screen` to keep Qt's ownership rules
        simple.
        """
        current = self._session_screen._data  # noqa: SLF001
        new_data = SessionScreenData(
            project_name=current.project_name,
            session_name=current.session_name,
            active_tab=current.active_tab,
            sources=current.sources + (card,),
            merger=current.merger,
            output=current.output,
        )
        self._source_modules.append(module)
        self._replace_session_screen(new_data)

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

    def _on_onboarding_dismissed(self) -> None:
        """Drop the overlay reference after the user dismisses it.

        The overlay has already hidden itself; we release our handle
        so Qt can garbage-collect the widget. The persistent flag was
        written inside :meth:`OnboardingOverlay._on_dismiss_clicked`,
        so further launches will see ``is_first_run() is False``.
        """
        overlay = self._onboarding_overlay
        self._onboarding_overlay = None
        if overlay is not None:
            overlay.deleteLater()

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
