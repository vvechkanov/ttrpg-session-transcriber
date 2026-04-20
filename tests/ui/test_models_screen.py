"""P1b — tests for the Models management screen.

Covers :class:`ui.shell.screens.models_screen.ModelsScreen` and its
menu integration in :class:`ui.shell.app.MainWindow`. All filesystem /
download-touching helpers (``is_backend_installed``,
``installed_size_bytes``, ``uninstall_backend``,
``ensure_backend_installed``) are monkey-patched so the tests never hit
real bundles, HuggingFace, or the user's tracked install directory.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QMessageBox, QPushButton

from core.backend_installers import BACKENDS, BackendId
from ui.shell.screens import models_screen as models_screen_mod
from ui.shell.screens.models_screen import ModelsScreen, _format_size


# ── _format_size (pure helper, no Qt) ──────────────────────────────────


class TestFormatSize:
    def test_zero_is_zero_mb(self):
        assert _format_size(0) == "0 MB"

    def test_negative_also_zero(self):
        # Defensive: negative inputs clamp to 0.
        assert _format_size(-5) == "0 MB"

    def test_small_bytes_round_to_zero_mb(self):
        assert _format_size(500) == "0 MB"

    def test_500_mb(self):
        assert _format_size(500 * 1024 * 1024) == "500 MB"

    def test_just_below_1_gb_stays_mb(self):
        # 1023 MB — integer MB display up until 1 GB.
        assert _format_size(1023 * 1024 * 1024) == "1023 MB"

    def test_3_gb_is_one_decimal(self):
        assert _format_size(3 * 1024 * 1024 * 1024) == "3.0 GB"

    def test_3_point_5_gb(self):
        # 3.5 GB exactly.
        assert _format_size(int(3.5 * 1024 * 1024 * 1024)) == "3.5 GB"


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def patched_backends(monkeypatch):
    """Return a helper with mutable state for each backend.

    Tests drive ``state[bid]['installed']`` / ``['size']`` and the
    corresponding ``is_backend_installed`` / ``installed_size_bytes``
    patched into ``models_screen`` respect those values.
    """
    state: dict[BackendId, dict[str, object]] = {
        bid: {"installed": False, "size": 0} for bid in BACKENDS
    }

    def _is_installed(bid: BackendId) -> bool:
        return bool(state[bid]["installed"])

    def _installed_size(bid: BackendId) -> int:
        return int(state[bid]["size"])

    monkeypatch.setattr(models_screen_mod, "is_backend_installed", _is_installed)
    monkeypatch.setattr(models_screen_mod, "installed_size_bytes", _installed_size)
    return state


# ── Screen rendering ────────────────────────────────────────────────────


@pytest.mark.gui
class TestModelsScreenRendering:
    def test_one_row_per_registered_backend(self, qtbot, patched_backends):
        screen = ModelsScreen()
        qtbot.addWidget(screen)
        assert len(screen._rows) == len(BACKENDS)  # noqa: SLF001
        # All registered BackendIds are represented exactly once.
        row_ids = {row.backend_id for row in screen._rows}  # noqa: SLF001
        assert row_ids == set(BACKENDS.keys())

    def test_installed_backend_shows_uninstall_button(
        self, qtbot, patched_backends
    ):
        bid = next(iter(BACKENDS))
        patched_backends[bid]["installed"] = True
        patched_backends[bid]["size"] = 948 * 1024 * 1024

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        row = _row_for(screen, bid)
        assert "установлена" in row._status_chip.text()  # noqa: SLF001
        assert "не установлена" not in row._status_chip.text()  # noqa: SLF001
        assert row._action_button.text() == "Удалить"  # noqa: SLF001
        assert row._size_label.text() == "948 MB"  # noqa: SLF001

    def test_not_installed_backend_shows_install_button(
        self, qtbot, patched_backends
    ):
        bid = next(iter(BACKENDS))
        patched_backends[bid]["installed"] = False

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        row = _row_for(screen, bid)
        assert "не установлена" in row._status_chip.text()  # noqa: SLF001
        assert row._action_button.text() == "Установить"  # noqa: SLF001
        # Approx download size is prefixed with "~".
        assert row._size_label.text().startswith("~")  # noqa: SLF001

    def test_total_on_disk_sums_installed_backends(
        self, qtbot, patched_backends
    ):
        # Install first backend with 500 MB, leave others uninstalled.
        bids = list(BACKENDS)
        patched_backends[bids[0]]["installed"] = True
        patched_backends[bids[0]]["size"] = 500 * 1024 * 1024
        if len(bids) > 1:
            patched_backends[bids[1]]["installed"] = True
            patched_backends[bids[1]]["size"] = 300 * 1024 * 1024
            expected_total = "800 MB"
        else:
            expected_total = "500 MB"

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        assert screen._total_label.text() == f"Всего на диске: {expected_total}"  # noqa: SLF001

    def test_total_on_disk_zero_when_nothing_installed(
        self, qtbot, patched_backends
    ):
        screen = ModelsScreen()
        qtbot.addWidget(screen)
        assert screen._total_label.text() == "Всего на диске: 0 MB"  # noqa: SLF001


# ── Uninstall flow ──────────────────────────────────────────────────────


@pytest.mark.gui
class TestUninstallAction:
    def test_confirm_yes_calls_uninstall_backend(
        self, qtbot, patched_backends, monkeypatch
    ):
        bid = next(iter(BACKENDS))
        patched_backends[bid]["installed"] = True
        patched_backends[bid]["size"] = 100 * 1024 * 1024

        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes),
        )

        called: list[BackendId] = []

        def _fake_uninstall(b: BackendId) -> None:
            called.append(b)
            patched_backends[b]["installed"] = False
            patched_backends[b]["size"] = 0

        monkeypatch.setattr(models_screen_mod, "uninstall_backend", _fake_uninstall)

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        row = _row_for(screen, bid)
        row._action_button.click()  # noqa: SLF001

        assert called == [bid]
        # After refresh, row should reflect "not installed".
        assert row._action_button.text() == "Установить"  # noqa: SLF001
        assert "не установлена" in row._status_chip.text()  # noqa: SLF001

    def test_confirm_no_does_nothing(
        self, qtbot, patched_backends, monkeypatch
    ):
        bid = next(iter(BACKENDS))
        patched_backends[bid]["installed"] = True
        patched_backends[bid]["size"] = 100 * 1024 * 1024

        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.No),
        )

        called: list[BackendId] = []
        monkeypatch.setattr(
            models_screen_mod,
            "uninstall_backend",
            lambda b: called.append(b),
        )

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        row = _row_for(screen, bid)
        row._action_button.click()  # noqa: SLF001

        assert called == []
        # Row remains "installed".
        assert row._action_button.text() == "Удалить"  # noqa: SLF001

    def test_uninstall_error_shows_critical(
        self, qtbot, patched_backends, monkeypatch
    ):
        bid = next(iter(BACKENDS))
        patched_backends[bid]["installed"] = True
        patched_backends[bid]["size"] = 100 * 1024 * 1024

        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes),
        )

        def _raise(b: BackendId) -> None:
            raise RuntimeError("disk error")

        monkeypatch.setattr(models_screen_mod, "uninstall_backend", _raise)

        critical_calls: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            staticmethod(
                lambda *a, **kw: critical_calls.append(a[-1] if a else "")
                or QMessageBox.StandardButton.Ok
            ),
        )

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        row = _row_for(screen, bid)
        row._action_button.click()  # noqa: SLF001

        assert len(critical_calls) == 1
        assert "disk error" in critical_calls[0]


# ── Install flow ────────────────────────────────────────────────────────


@pytest.mark.gui
class TestInstallAction:
    def test_install_click_calls_ensure_backend_installed(
        self, qtbot, patched_backends, monkeypatch
    ):
        bid = next(iter(BACKENDS))
        patched_backends[bid]["installed"] = False

        calls: list[tuple[BackendId, object]] = []

        def _fake_ensure(b: BackendId, *, parent=None) -> bool:
            calls.append((b, parent))
            # Simulate successful install
            patched_backends[b]["installed"] = True
            patched_backends[b]["size"] = 950 * 1024 * 1024
            return True

        monkeypatch.setattr(
            models_screen_mod, "ensure_backend_installed", _fake_ensure
        )

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        row = _row_for(screen, bid)
        row._action_button.click()  # noqa: SLF001

        assert len(calls) == 1
        assert calls[0][0] == bid
        assert calls[0][1] is screen
        # Row should refresh to "installed".
        assert row._action_button.text() == "Удалить"  # noqa: SLF001
        assert "установлена" in row._status_chip.text()  # noqa: SLF001

    def test_install_error_shows_critical_then_refreshes(
        self, qtbot, patched_backends, monkeypatch
    ):
        bid = next(iter(BACKENDS))
        patched_backends[bid]["installed"] = False

        def _raise(b: BackendId, *, parent=None) -> bool:
            raise RuntimeError("network broken")

        monkeypatch.setattr(models_screen_mod, "ensure_backend_installed", _raise)

        critical_calls: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            staticmethod(
                lambda *a, **kw: critical_calls.append(a[-1] if a else "")
                or QMessageBox.StandardButton.Ok
            ),
        )

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        row = _row_for(screen, bid)
        row._action_button.click()  # noqa: SLF001

        assert len(critical_calls) == 1
        assert "network broken" in critical_calls[0]
        # Row stayed "not installed".
        assert row._action_button.text() == "Установить"  # noqa: SLF001


# ── Refresh propagation ─────────────────────────────────────────────────


@pytest.mark.gui
class TestRefresh:
    def test_refresh_after_flip_updates_chip(
        self, qtbot, patched_backends
    ):
        bid = next(iter(BACKENDS))
        patched_backends[bid]["installed"] = False

        screen = ModelsScreen()
        qtbot.addWidget(screen)
        row = _row_for(screen, bid)
        assert "не установлена" in row._status_chip.text()  # noqa: SLF001

        # Flip state and refresh from outside.
        patched_backends[bid]["installed"] = True
        patched_backends[bid]["size"] = 200 * 1024 * 1024
        screen.refresh()

        assert "установлена" in row._status_chip.text()  # noqa: SLF001
        assert "не установлена" not in row._status_chip.text()  # noqa: SLF001
        assert row._size_label.text() == "200 MB"  # noqa: SLF001
        # Total label picks up the new size too.
        assert "200 MB" in screen._total_label.text()  # noqa: SLF001


# ── Menu integration ────────────────────────────────────────────────────


@pytest.mark.gui
class TestMenuIntegration:
    def test_menu_entry_exists_and_opens_models_screen(
        self, qtbot, monkeypatch
    ):
        from ui.shell import app as app_mod
        from ui.shell.app import MainWindow

        # Prevent real dialog exec — we just verify ModelsScreen is
        # instantiated with parent=window.
        constructed: list[object] = []

        class _FakeDialog:
            def __init__(self, parent=None):
                constructed.append(parent)

            def exec(self) -> int:
                return 0

        monkeypatch.setattr(app_mod, "ModelsScreen", _FakeDialog)

        window = MainWindow()
        qtbot.addWidget(window)

        # Find the "Модели" menu and its first action.
        menu_bar = window.menuBar()
        models_menu = None
        for action in menu_bar.actions():
            # QMenu.title() keeps the ampersand; strip it for match.
            title = action.text().replace("&", "")
            if title == "Модели":
                models_menu = action.menu()
                break
        assert models_menu is not None, "'Модели' menu was not added"

        actions = models_menu.actions()
        assert len(actions) >= 1
        manage_action = actions[0]
        assert "Управление моделями" in manage_action.text()

        manage_action.trigger()
        assert constructed == [window]


# ── helpers ─────────────────────────────────────────────────────────────


def _row_for(screen: ModelsScreen, bid: BackendId):
    for row in screen._rows:  # noqa: SLF001
        if row.backend_id == bid:
            return row
    raise AssertionError(f"no row for {bid}")
