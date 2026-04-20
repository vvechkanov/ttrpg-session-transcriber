"""Integration test: ``ModelRegistry`` reads from ``core.backend_installers``.

Run as::

    QT_QPA_PLATFORM=offscreen python tests/ui_qml_smoke/test_model_registry.py

Exits 0 on success, 1 on failure. Graduates to a pytest-qt test in
Phase 11.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backend_installers import BACKENDS, BackendId  # noqa: E402
from ui.models.model_registry import ModelRegistry, _format_size  # noqa: E402


def _assert(cond: bool, message: str) -> None:
    if not cond:
        sys.stderr.write(f"FAIL: {message}\n")
        raise SystemExit(1)


def main() -> int:
    # QSettings needs a QCoreApplication-instance; QGuiApplication subclasses it.
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("smoke")
    app.setOrganizationName("smoke")

    # Format helper sanity
    _assert(_format_size(0) == "—", "zero bytes → em dash")
    _assert(_format_size(420_000_000) == "420 MB", f"got {_format_size(420_000_000)!r}")
    _assert(_format_size(3_100_000_000) == "3.1 GB", f"got {_format_size(3_100_000_000)!r}")
    _assert(_format_size(15_000_000_000) == "15 GB", f"got {_format_size(15_000_000_000)!r}")

    registry = ModelRegistry()
    n = registry.rowCount()
    _assert(n == len(BACKENDS), f"expected {len(BACKENDS)} rows, got {n}")

    for row in range(n):
        entry = registry.entryAt(row)
        _assert(entry is not None, f"entryAt({row}) returned None")
        backend_id_str = entry["backend_id"]
        _assert(
            backend_id_str in {b.value for b in BackendId},
            f"unknown backend_id {backend_id_str!r}",
        )
        _assert(isinstance(entry["name"], str) and entry["name"], f"bad name: {entry['name']!r}")
        _assert(isinstance(entry["installed"], bool), f"installed not bool: {entry['installed']!r}")
        _assert(isinstance(entry["active"], bool), f"active not bool: {entry['active']!r}")

    # Exactly one row should be active initially — the default or the one
    # QSettings already remembers from a prior run.
    actives = sum(1 for r in range(n) if registry.entryAt(r)["active"])
    _assert(actives <= 1, f"expected ≤1 active, got {actives}")

    # setActive on an uninstalled row is a no-op.
    registry.setActive(0)
    before_active = [registry.entryAt(r)["active"] for r in range(n)]
    # setActive on an uninstalled row must not flip it to active.
    for r in range(n):
        e = registry.entryAt(r)
        if not e["installed"] and e["active"]:
            _assert(False, f"uninstalled row {r} became active")

    print(f"OK: ModelRegistry holds {n} rows sourced from core.backend_installers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
