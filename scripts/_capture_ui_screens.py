"""One-shot UI screenshotting for UX review (not part of the product)."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "screenshots" / "ux-review"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO))

from ui.shell.app import MainWindow, _build_session_from_dir  # noqa: E402
from ui.shell.add_source_dialog import AddSourceDialog  # noqa: E402


def _save(widget, name: str) -> None:
    widget.show()
    QApplication.processEvents()
    widget.repaint()
    QApplication.processEvents()
    pix = widget.grab()
    path = OUT / f"{name}.png"
    pix.save(str(path))
    sys.stdout.buffer.write(f"saved {name}.png ({pix.width()}x{pix.height()})\n".encode("utf-8"))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Empty main window — what user sees on launch.
    mw = MainWindow()
    _save(mw, "01_empty_main_window")

    # 2. Main window with a fixture session loaded.
    fixture = REPO / "tests" / "fixtures" / "e2e_p2" / "session"
    if fixture.is_dir():
        try:
            data, modules = _build_session_from_dir(fixture)
            mw._session_dir = fixture  # type: ignore[attr-defined]
            mw._source_modules = modules  # type: ignore[attr-defined]
            mw._replace_session_screen(data)  # type: ignore[attr-defined]
            _save(mw, "02_session_loaded")
        except Exception as exc:
            print(f"session load skipped: {exc}")

    # 3. AddSourceDialog — parser picker.
    dlg = AddSourceDialog(parent=None)
    _save(dlg, "03_add_source_dialog")

    mw.close()
    dlg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
