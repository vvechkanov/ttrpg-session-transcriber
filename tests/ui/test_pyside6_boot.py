"""Smoke test: PySide6 skeleton boots without exceptions."""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")


@pytest.mark.gui
def test_main_window_opens(qtbot):
    from ui.shell.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle().startswith("Session Transcriber")
    assert window.width() == 1400
    assert window.height() == 900
