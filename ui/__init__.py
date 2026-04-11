"""UI layer — CLI and GUI entry points. Depends only on core.

Since ADR-017 the default GUI is the PySide6 shell in
:mod:`ui.shell.app`; the legacy tkinter entry point lives on as
``ui.gui_legacy`` for a transitional release and is no longer wired
into ``ui.main()``.
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) == 1:
        from ui.shell.app import main as qt_main
        return qt_main()
    from ui.cli import cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
