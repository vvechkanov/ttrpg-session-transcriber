"""Tests for :class:`ui.shell.screens.EmptyStateScreen` (P0a + P2a).

Covers:
    * The primary button ("Выбрать папку…") emits
      ``pick_folder_requested`` when clicked.
    * Dropping a directory on the drop zone emits
      ``folder_dropped(Path)`` with the right path.
    * Dropping a single file on the drop zone does not emit
      ``folder_dropped`` and surfaces a :class:`QMessageBox.warning`.
    * P2a — "Недавние сессии" section is rendered only when the
      ``recent`` list is non-empty, rows emit
      ``recent_session_selected`` on click, and the "очистить" button
      wipes persistence and the rendered rows.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QMessageBox, QPushButton

from core.recent_sessions import RecentSession
from ui.shell.screens import EmptyStateScreen
from ui.shell.screens import empty_state_screen as ess_module


def _mime_with_urls(urls: list[str]) -> QMimeData:
    """Build a QMimeData carrying the given local-file URLs."""
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(u) for u in urls])
    return mime


@pytest.mark.gui
class TestEmptyStateScreen:
    def test_screen_builds(self, qtbot):
        screen = EmptyStateScreen()
        qtbot.addWidget(screen)
        screen.show()
        qtbot.waitExposed(screen)
        assert screen.isVisible()

    def test_pick_button_emits_pick_folder_requested(self, qtbot):
        screen = EmptyStateScreen()
        qtbot.addWidget(screen)

        pick_buttons = [
            b for b in screen.findChildren(QPushButton)
            if "Выбрать папку" in b.text()
        ]
        assert len(pick_buttons) == 1

        with qtbot.waitSignal(screen.pick_folder_requested, timeout=1000):
            pick_buttons[0].click()

    def test_folder_drop_emits_folder_dropped(
        self, qtbot, tmp_path: Path
    ):
        screen = EmptyStateScreen()
        qtbot.addWidget(screen)

        received: list[Path] = []
        screen.folder_dropped.connect(received.append)

        folder = tmp_path / "session"
        folder.mkdir()

        # Route through the testable mime handler — synthesising a real
        # QDropEvent from Python causes the mimeData() pointer to be
        # unwrapped as a generic QObject by the bindings.
        screen._drop_zone.handle_mime_drop(  # noqa: SLF001
            _mime_with_urls([str(folder)])
        )
        assert received == [folder]

    def test_file_drop_emits_warning_and_no_signal(
        self, qtbot, tmp_path: Path, monkeypatch
    ):
        screen = EmptyStateScreen()
        qtbot.addWidget(screen)

        received: list[Path] = []
        screen.folder_dropped.connect(received.append)

        calls: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *args, **kwargs: calls.append("warning") or QMessageBox.Ok,
        )

        some_file = tmp_path / "note.txt"
        some_file.write_text("hi", encoding="utf-8")

        screen._drop_zone.handle_mime_drop(  # noqa: SLF001
            _mime_with_urls([str(some_file)])
        )
        assert received == []
        assert calls == ["warning"]

    def test_multi_item_drop_emits_warning_and_no_signal(
        self, qtbot, tmp_path: Path, monkeypatch
    ):
        screen = EmptyStateScreen()
        qtbot.addWidget(screen)

        received: list[Path] = []
        screen.folder_dropped.connect(received.append)

        calls: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *args, **kwargs: calls.append("warning") or QMessageBox.Ok,
        )

        a = tmp_path / "a"
        a.mkdir()
        b = tmp_path / "b"
        b.mkdir()

        screen._drop_zone.handle_mime_drop(  # noqa: SLF001
            _mime_with_urls([str(a), str(b)])
        )
        assert received == []
        assert calls == ["warning"]

    def test_drag_active_toggle_changes_border_state(self, qtbot):
        """The drop-zone highlight flag flips via ``set_drag_active``.

        The real ``dragEnterEvent`` / ``dragLeaveEvent`` handlers
        delegate to this method, so testing the toggle covers the
        border feedback without synthesising a drag event.
        """
        screen = EmptyStateScreen()
        qtbot.addWidget(screen)

        zone = screen._drop_zone  # noqa: SLF001
        assert zone.is_drag_active() is False
        zone.set_drag_active(True)
        assert zone.is_drag_active() is True
        zone.set_drag_active(False)
        assert zone.is_drag_active() is False


# ── P2a — Recent sessions list ─────────────────────────────────────────


@pytest.mark.gui
class TestRecentSessions:
    def test_constructor_accepts_recent_kwarg(self, qtbot):
        # Keyword-only and optional with default.
        screen = EmptyStateScreen(recent=())
        qtbot.addWidget(screen)
        assert screen.isVisible() is False  # not shown yet, but built

    def test_no_recents_hides_section(self, qtbot):
        screen = EmptyStateScreen(recent=())
        qtbot.addWidget(screen)
        # The section container must exist but be hidden so the empty
        # state doesn't show a lonely "Недавние сессии" header.
        assert screen._recent_section.isHidden() is True  # noqa: SLF001

    def test_n_recents_render_n_rows(self, qtbot, tmp_path: Path):
        sessions = tuple(
            RecentSession(
                path=(tmp_path / f"s{i}"), opened_at=float(time.time() - i)
            )
            for i in range(3)
        )
        # Ensure the dirs exist so the row titles aren't empty. The
        # screen doesn't check for existence itself — that's the job
        # of ``core.recent_sessions.load_recent``.
        for s in sessions:
            s.path.mkdir()

        screen = EmptyStateScreen(recent=sessions)
        qtbot.addWidget(screen)

        rows = screen._rows_container.findChildren(  # noqa: SLF001
            ess_module._RecentSessionRow
        )
        assert len(rows) == 3

    def test_open_row_emits_recent_session_selected(
        self, qtbot, tmp_path: Path
    ):
        wanted = tmp_path / "session-42"
        wanted.mkdir()
        sessions = (
            RecentSession(path=wanted, opened_at=float(time.time())),
        )

        screen = EmptyStateScreen(recent=sessions)
        qtbot.addWidget(screen)

        received: list[Path] = []
        screen.recent_session_selected.connect(received.append)

        # Click the "открыть" button on the first (and only) row.
        rows = screen._rows_container.findChildren(  # noqa: SLF001
            ess_module._RecentSessionRow
        )
        assert len(rows) == 1
        rows[0]._open_btn.click()  # noqa: SLF001

        assert received == [wanted]

    def test_clear_button_wipes_and_refreshes(
        self, qtbot, tmp_path: Path, monkeypatch
    ):
        session = tmp_path / "session-1"
        session.mkdir()
        sessions = (
            RecentSession(path=session, opened_at=float(time.time())),
        )

        screen = EmptyStateScreen(recent=sessions)
        qtbot.addWidget(screen)

        # Sanity: section not hidden, one row.
        assert screen._recent_section.isHidden() is False  # noqa: SLF001
        rows = screen._rows_container.findChildren(  # noqa: SLF001
            ess_module._RecentSessionRow
        )
        assert len(rows) == 1

        clear_calls: list[bool] = []

        from core import recent_sessions as rs_module

        monkeypatch.setattr(
            rs_module, "clear_recent", lambda: clear_calls.append(True)
        )

        screen._clear_button.click()  # noqa: SLF001

        assert clear_calls == [True]
        # Section should be hidden now that the list is empty.
        assert screen._recent_section.isHidden() is True  # noqa: SLF001
        rows_after = screen._rows_container.findChildren(  # noqa: SLF001
            ess_module._RecentSessionRow
        )
        assert rows_after == []

    def test_refresh_recent_is_idempotent(self, qtbot, tmp_path: Path):
        """Calling refresh_recent multiple times should not leak rows."""
        session = tmp_path / "only"
        session.mkdir()
        sessions = (
            RecentSession(path=session, opened_at=float(time.time())),
        )

        screen = EmptyStateScreen(recent=sessions)
        qtbot.addWidget(screen)

        # Call refresh again with the same data — row count stable at 1.
        screen.refresh_recent(sessions)
        rows = screen._rows_container.findChildren(  # noqa: SLF001
            ess_module._RecentSessionRow
        )
        assert len(rows) == 1

        # Shrink to empty — rows disappear.
        screen.refresh_recent(())
        rows_empty = screen._rows_container.findChildren(  # noqa: SLF001
            ess_module._RecentSessionRow
        )
        assert rows_empty == []


# ── Relative-time formatter ────────────────────────────────────────────


class TestFormatRelativeTime:
    def test_today(self):
        from datetime import datetime

        now = datetime(2026, 4, 19, 15, 0)
        ts = datetime(2026, 4, 19, 9, 0).timestamp()
        assert ess_module._format_relative_time(ts, now=now) == "сегодня"

    def test_yesterday(self):
        from datetime import datetime

        now = datetime(2026, 4, 19, 15, 0)
        ts = datetime(2026, 4, 18, 20, 0).timestamp()
        assert ess_module._format_relative_time(ts, now=now) == "вчера"

    def test_three_days_ago(self):
        from datetime import datetime

        now = datetime(2026, 4, 19, 15, 0)
        ts = datetime(2026, 4, 16, 12, 0).timestamp()
        assert ess_module._format_relative_time(ts, now=now) == "3 дн. назад"

    def test_older_than_week_uses_russian_month(self):
        from datetime import datetime

        now = datetime(2026, 4, 19, 15, 0)
        ts = datetime(2026, 4, 3, 12, 0).timestamp()
        assert ess_module._format_relative_time(ts, now=now) == "3 апр"
