"""Tests for :class:`ui.shell.screens.EmptyStateScreen` (P0a).

Covers:
    * The primary button ("Выбрать папку…") emits
      ``pick_folder_requested`` when clicked.
    * Dropping a directory on the drop zone emits
      ``folder_dropped(Path)`` with the right path.
    * Dropping a single file on the drop zone does not emit
      ``folder_dropped`` and surfaces a :class:`QMessageBox.warning`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QMessageBox, QPushButton

from ui.shell.screens import EmptyStateScreen


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
