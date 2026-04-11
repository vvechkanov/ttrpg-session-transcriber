"""UI layer — CLI and GUI entry points. Depends only on core."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) == 1:
        from ui.gui import gui_main
        return gui_main()
    from ui.cli import cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
