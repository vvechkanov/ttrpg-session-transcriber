"""Dev/CI utility — install GigaAM bundle without GUI.

Это НЕ user-facing скрипт. Пользователь ставит модели через
``launcher/installer_ui.py`` или in-app modal в ``ui/gui.py``. Этот скрипт
нужен разработчикам, CI smoke-тестам и для troubleshooting.
"""

from __future__ import annotations

import argparse
import sys

from core.backend_installers import BackendId, install_backend


def main() -> int:
    ap = argparse.ArgumentParser(prog="download_gigaam")
    ap.add_argument(
        "--backend",
        default=BackendId.GIGAAM_RNNT_FP32.value,
        choices=[b.value for b in BackendId],
    )
    args = ap.parse_args()

    def _prog(fraction: float, msg: str) -> None:
        sys.stdout.write(f"\r[{int(fraction * 100):3d}%] {msg:<60}")
        sys.stdout.flush()

    install_backend(BackendId(args.backend), progress=_prog)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
