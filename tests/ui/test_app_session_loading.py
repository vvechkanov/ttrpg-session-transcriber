"""Phase 9 — MainWindow session loading smoke tests.

Covers the Phase 9 surface of ``ui/shell/app.py``:

    * ``_build_session_from_dir`` constructs SessionScreenData + a parallel
      module list for a real session folder (audio + fvtt-log).
    * ``_load_session`` swaps the central widget and reconnects signals
      without crashing.
    * ``_build_pipeline_params`` honours module state (variant / device).
    * ``_open_module_drawer`` falls through to the demo stub when a
      module has no ``ui_config``.
    * The folder-picker path (``_on_open_session``) delegates to
      ``_load_session`` with the directory the dialog returned.

Heavy pipeline execution is out of scope here — the Phase 6 run-controller
tests already cover that. We only care that Phase 9's wiring is coherent
and doesn't regress when a user opens a real folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")


# ── helpers ─────────────────────────────────────────────────────────────


def _make_session(tmp_path: Path, *, with_chat: bool, with_audio: bool) -> Path:
    session = tmp_path / "Campaign X" / "2026-04-10"
    session.mkdir(parents=True)
    if with_audio:
        (session / "alice.flac").write_bytes(b"")
        (session / "bob.flac").write_bytes(b"")
        (session / "craig.flac").write_bytes(b"")  # should be filtered out
    if with_chat:
        (session / "fvtt-log-2026-04-10.txt").write_text(
            "line1\nline2\nline3\n", encoding="utf-8"
        )
    return session


# ── _build_session_from_dir (no Qt needed) ──────────────────────────────


class TestBuildSessionFromDir:
    def test_audio_and_chat(self, tmp_path: Path):
        from ui.shell.app import _build_session_from_dir

        session = _make_session(tmp_path, with_chat=True, with_audio=True)
        data, modules = _build_session_from_dir(session)

        assert data.project_name == "Campaign X"
        assert data.session_name == "2026-04-10"
        # 2 source cards: audio + chat
        assert len(data.sources) == 2
        audio_card, chat_card = data.sources
        assert audio_card.title == "Аудио"
        assert "alice.flac" in audio_card.files
        assert "bob.flac" in audio_card.files
        assert "craig.flac" not in audio_card.files
        assert audio_card.status == "ready"
        assert chat_card.title == "Foundry VTT чат"
        assert chat_card.files == ("fvtt-log-2026-04-10.txt",)
        assert "3 строк" in (chat_card.files_hint or "")

        # Modules parallel to cards
        assert len(modules) == 2
        assert getattr(modules[0], "name", None) == "gigaam"
        assert getattr(modules[1], "name", None) == "fvtt-chat"

    def test_audio_only_no_chat(self, tmp_path: Path):
        from ui.shell.app import _build_session_from_dir

        session = _make_session(tmp_path, with_chat=False, with_audio=True)
        data, modules = _build_session_from_dir(session)

        assert len(data.sources) == 1
        assert data.sources[0].title == "Аудио"
        assert len(modules) == 1

    def test_empty_session_flags_warning(self, tmp_path: Path):
        from ui.shell.app import _build_session_from_dir

        session = _make_session(tmp_path, with_chat=False, with_audio=False)
        data, modules = _build_session_from_dir(session)

        assert len(data.sources) == 1
        assert data.sources[0].status == "warning"
        assert data.sources[0].files == ()
        assert len(modules) == 1  # gigaam module still constructed


# ── MainWindow wiring (requires Qt) ─────────────────────────────────────


@pytest.mark.gui
class TestMainWindowPhase9:
    def test_empty_window_opens_with_placeholder(self, qtbot):
        from ui.shell.app import MainWindow
        from ui.shell.screens import EmptyStateScreen

        window = MainWindow()
        qtbot.addWidget(window)
        assert window._session_dir is None
        assert window._source_modules == []
        # P0a — empty state screen is the initial central widget; the
        # full SessionScreen is built lazily on first _load_session.
        assert window._session_screen is None
        assert isinstance(window.centralWidget(), EmptyStateScreen)

    def test_load_session_populates_screen_and_modules(self, qtbot, tmp_path: Path):
        from ui.shell.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        session = _make_session(tmp_path, with_chat=True, with_audio=True)
        window._load_session(session)

        assert window._session_dir == session
        assert len(window._source_modules) == 2
        # central widget was swapped
        data = window._session_screen._data  # noqa: SLF001
        assert data.session_name == "2026-04-10"
        assert len(data.sources) == 2

        # Signals on the fresh SessionScreen must be reconnected — emit
        # run_clicked and verify the controller.start slot was exercised.
        started: list[bool] = []
        window._run_controller.start = (  # type: ignore[method-assign]
            lambda request: started.append(True) or True
        )
        window._session_screen.run_clicked.emit()
        assert started == [True]

    def test_load_session_missing_dir_shows_warning(
        self, qtbot, tmp_path: Path, monkeypatch
    ):
        from ui.shell.app import MainWindow
        from PySide6.QtWidgets import QMessageBox

        window = MainWindow()
        qtbot.addWidget(window)

        calls: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *args, **kwargs: calls.append("warning") or QMessageBox.Ok,
        )
        window._load_session(tmp_path / "does-not-exist")
        assert calls == ["warning"]
        assert window._session_dir is None

    def test_build_pipeline_params_reads_gigaam_state(self, qtbot, tmp_path: Path):
        from ui.shell.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        session = _make_session(tmp_path, with_chat=False, with_audio=True)
        window._load_session(session)

        gigaam = window._source_modules[0]
        # Forcing attributes on the instance so _build_pipeline_params
        # picks them up regardless of the module's own defaults.
        gigaam.device = "cuda"
        gigaam.num_threads = 8

        params = window._build_pipeline_params()
        assert params.speech_backend == "gigaam"
        assert params.device == "cuda"
        assert params.num_threads == 8
        assert params.merger == "script"
        assert params.renderer == "plain-text"
        assert params.output_filename == "merged.txt"

    def test_run_without_session_shows_info_and_no_controller(
        self, qtbot, monkeypatch
    ):
        from ui.shell.app import MainWindow
        from PySide6.QtWidgets import QMessageBox

        window = MainWindow()
        qtbot.addWidget(window)

        calls: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "information",
            lambda *args, **kwargs: calls.append("info") or QMessageBox.Ok,
        )

        # Sanity: controller should not be started if no session is open.
        started: list[bool] = []
        monkeypatch.setattr(
            window._run_controller,
            "start",
            lambda request: started.append(True) or True,
        )

        window._on_run_clicked()
        assert calls == ["info"]
        assert started == []

    def test_open_module_drawer_falls_back_to_demo_when_no_ui_config(
        self, qtbot
    ):
        from ui.shell.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        class _Bare:
            pass

        window._open_module_drawer(
            module=_Bare(), title="T", subtitle="S"
        )
        # Drawer should be visible with a panel attached
        assert window._settings_drawer is not None

    def test_on_open_session_delegates_to_load(
        self, qtbot, tmp_path: Path, monkeypatch
    ):
        from ui.shell.app import MainWindow
        from PySide6.QtWidgets import QFileDialog

        session = _make_session(tmp_path, with_chat=False, with_audio=True)
        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *args, **kwargs: str(session)),
        )

        window = MainWindow()
        qtbot.addWidget(window)
        window._on_open_session()

        assert window._session_dir == session
        assert len(window._source_modules) >= 1

    def test_on_open_session_cancelled_is_noop(
        self, qtbot, monkeypatch
    ):
        from ui.shell.app import MainWindow
        from PySide6.QtWidgets import QFileDialog

        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *args, **kwargs: ""),
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window._on_open_session()
        assert window._session_dir is None


# ── P1a — window-level folder drag-and-drop ─────────────────────────────


@pytest.mark.gui
class TestMainWindowFolderDrop:
    """Covers ``MainWindow.handle_mime_drop`` → ``_load_session``.

    Synthesising a real :class:`QDropEvent` from Python is fragile —
    the PySide6 bindings unwrap the event's ``mimeData()`` pointer as a
    generic ``QObject`` once it round-trips through the C++ layer,
    which makes ``hasUrls()`` raise. We exercise the drop-handling
    logic through the testable ``handle_mime_drop`` entry point, which
    takes a plain :class:`QMimeData`. In production Qt constructs the
    event itself and this indirection isn't needed.
    """

    @staticmethod
    def _mime(urls: list[str]):
        from PySide6.QtCore import QMimeData, QUrl

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(u) for u in urls])
        return mime

    def test_folder_drop_calls_load_session(
        self, qtbot, tmp_path: Path, monkeypatch
    ):
        from ui.shell.app import MainWindow

        session = _make_session(tmp_path, with_chat=False, with_audio=True)

        window = MainWindow()
        qtbot.addWidget(window)

        calls: list[Path] = []
        monkeypatch.setattr(
            window, "_load_session", lambda p: calls.append(p)
        )

        window.handle_mime_drop(self._mime([str(session)]))
        assert calls == [session]

    def test_file_drop_is_ignored(
        self, qtbot, tmp_path: Path, monkeypatch
    ):
        from ui.shell.app import MainWindow

        some_file = tmp_path / "just-a-file.txt"
        some_file.write_text("hi", encoding="utf-8")

        window = MainWindow()
        qtbot.addWidget(window)

        calls: list[Path] = []
        monkeypatch.setattr(
            window, "_load_session", lambda p: calls.append(p)
        )

        window.handle_mime_drop(self._mime([str(some_file)]))
        assert calls == []
        # Window should remain in the empty state (no session loaded).
        assert window._session_dir is None

    def test_multi_item_drop_is_ignored(
        self, qtbot, tmp_path: Path, monkeypatch
    ):
        from ui.shell.app import MainWindow

        session_a = _make_session(
            tmp_path / "a", with_chat=False, with_audio=True
        )
        session_b = _make_session(
            tmp_path / "b", with_chat=False, with_audio=True
        )

        window = MainWindow()
        qtbot.addWidget(window)

        calls: list[Path] = []
        monkeypatch.setattr(
            window, "_load_session", lambda p: calls.append(p)
        )

        window.handle_mime_drop(
            self._mime([str(session_a), str(session_b)])
        )
        assert calls == []


# ── P2a / P2b — recent sessions and onboarding overlay wiring ────────────


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch):
    """Redirect recent-sessions and onboarding storage to ``tmp_path``.

    Every MainWindow test that touches onboarding / recents implicitly
    depends on :func:`core.recent_sessions.config_dir`; this fixture
    makes sure we never pollute the real user config dir.
    """
    target = tmp_path / "cfg"
    target.mkdir()
    from core import onboarding_state, recent_sessions

    monkeypatch.setattr(recent_sessions, "config_dir", lambda: target)
    monkeypatch.setattr(onboarding_state, "config_dir", lambda: target)
    return target


@pytest.mark.gui
class TestMainWindowRecentSessions:
    def test_load_session_calls_add_recent(
        self, qtbot, tmp_path: Path, monkeypatch, isolated_config: Path
    ):
        from ui.shell import app as app_module

        calls: list[Path] = []
        monkeypatch.setattr(
            app_module.recent_sessions,
            "add_recent",
            lambda p: calls.append(p) or (),
        )

        window = app_module.MainWindow()
        qtbot.addWidget(window)

        session = _make_session(
            tmp_path / "sess", with_chat=False, with_audio=True
        )
        window._load_session(session)

        assert calls == [session]

    def test_recent_session_selected_routes_to_load(
        self, qtbot, tmp_path: Path, monkeypatch, isolated_config: Path
    ):
        from ui.shell import app as app_module

        window = app_module.MainWindow()
        qtbot.addWidget(window)

        captured: list[Path] = []
        monkeypatch.setattr(
            window, "_load_session", lambda p: captured.append(p)
        )

        target = tmp_path / "some-session"
        target.mkdir()
        # Empty-state screen is still the central widget; emit directly.
        assert window._empty_state_screen is not None
        window._empty_state_screen.recent_session_selected.emit(target)

        assert captured == [target]


@pytest.mark.gui
class TestMainWindowOnboardingOverlay:
    def test_overlay_shown_on_first_run(
        self, qtbot, monkeypatch, isolated_config: Path
    ):
        from core import onboarding_state, recent_sessions
        from ui.shell import app as app_module

        monkeypatch.setattr(
            app_module.onboarding_state, "is_first_run", lambda: True
        )
        monkeypatch.setattr(
            app_module.recent_sessions, "load_recent", lambda: ()
        )

        window = app_module.MainWindow()
        qtbot.addWidget(window)

        assert window._onboarding_overlay is not None
        assert window._onboarding_overlay.isVisible() or not window.isVisible()
        # Silence unused imports warning
        _ = (onboarding_state, recent_sessions)

    def test_overlay_not_shown_when_not_first_run(
        self, qtbot, monkeypatch, isolated_config: Path
    ):
        from ui.shell import app as app_module

        monkeypatch.setattr(
            app_module.onboarding_state, "is_first_run", lambda: False
        )
        monkeypatch.setattr(
            app_module.recent_sessions, "load_recent", lambda: ()
        )

        window = app_module.MainWindow()
        qtbot.addWidget(window)
        assert window._onboarding_overlay is None

    def test_overlay_not_shown_when_recents_exist(
        self, qtbot, monkeypatch, tmp_path: Path, isolated_config: Path
    ):
        """First-run flag true BUT recents list non-empty → no overlay.

        A user who manually cleared the flag but has recent sessions
        has obviously used the app before, so we skip the welcome.
        """
        from core.recent_sessions import RecentSession
        from ui.shell import app as app_module

        session = tmp_path / "prev"
        session.mkdir()

        monkeypatch.setattr(
            app_module.onboarding_state, "is_first_run", lambda: True
        )
        monkeypatch.setattr(
            app_module.recent_sessions,
            "load_recent",
            lambda: (RecentSession(path=session, opened_at=100.0),),
        )

        window = app_module.MainWindow()
        qtbot.addWidget(window)
        assert window._onboarding_overlay is None
