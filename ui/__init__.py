"""UI layer — CLI and QML GUI entry points. Depends only on core.

The QML shell is the only GUI. The Phase 0..10 migration retired the
Qt Widgets entry point (``ui.shell``) and the tkinter legacy
(``ui.gui_legacy``); today ``python -m ui`` boots the QML loader at
:mod:`ui.app_qml`. A CLI flag path (``python -m ui --arg...``) still
routes to :mod:`ui.cli` for headless session processing.
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) == 1:
        from ui.app_qml import main as qml_main
        return qml_main()
    from ui.cli import cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
