"""UI walkthrough driver — programmatic 'clicks' + screenshots.

Runs the real MainWindow with a real session folder, exercises each
screen/dialog through its public API, and saves a PNG per state.

Not part of the product — ad-hoc QA tool.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "screenshots" / "walkthrough"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO))

SESSION = Path(r"C:\DND\Азланти\Cессии\Сессия 4 — копия")


def _save(widget, name: str) -> None:
    widget.show()
    QApplication.processEvents()
    widget.repaint()
    QApplication.processEvents()
    pix = widget.grab()
    pix.save(str(OUT / f"{name}.png"))
    sys.stdout.buffer.write(f"saved {name}.png ({pix.width()}x{pix.height()})\n".encode("utf-8"))


def main() -> int:
    from ui.shell.app import MainWindow
    from ui.shell.add_source_dialog import AddSourceDialog
    from ui.shell.screens import ModelsScreen
    from ui.widgets.source_card import SourceCard, SourceCardData

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Empty state.
    mw = MainWindow()
    _save(mw, "01_empty")

    # 2. Real session loaded.
    if not SESSION.is_dir():
        sys.stdout.buffer.write(f"SKIP: {SESSION} not found\n".encode("utf-8"))
    else:
        mw._load_session(SESSION)
        _save(mw, "02_session_loaded")

    # 3. ModelsScreen.
    models = ModelsScreen(parent=mw)
    models.show()
    QApplication.processEvents()
    _save(models, "03_models_screen")
    models.close()

    # 4. AddSourceDialog.
    add = AddSourceDialog(parent=mw)
    add.show()
    QApplication.processEvents()
    _save(add, "04_add_source_dialog")
    add.close()

    # 5. Source card State B — drop zone (no files found).
    card_b = SourceCard(
        SourceCardData(
            title="Foundry VTT чат-лог",
            subtitle="fvtt-chat parser",
            files=(),
            missing_hint="fvtt-log-*.txt",
            parser_key="fvtt-chat",
            status="warning",
            status_text="нет файлов",
        ),
    )
    card_b.resize(480, 280)
    _save(card_b, "05_source_card_state_B")

    # 6. Source card State C — multiple candidates with checkboxes.
    card_c = SourceCard(
        SourceCardData(
            title="Бой · FVTT encounter",
            subtitle="combat parser",
            files=("Бой 1.txt", "Бой 2.json", "combat_old.json"),
            candidate_files=("Бой 1.txt", "Бой 2.json", "combat_old.json"),
            selected_candidates=("Бой 1.txt", "Бой 2.json"),
            parser_key="combat",
            status="ready",
            status_text="готов",
        ),
    )
    card_c.resize(480, 320)
    _save(card_c, "06_source_card_state_C")

    mw.close()
    QTimer.singleShot(0, app.quit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
