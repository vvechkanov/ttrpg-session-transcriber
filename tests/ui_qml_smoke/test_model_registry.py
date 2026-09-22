"""``ModelRegistry`` — мост между ``core.backend_installers`` и экраном моделей.

Файл был скриптом с ``main()`` и ручными ``_assert``: pytest собирал из
него ноль тестов, то есть ни одна проверка ниже в CI не исполнялась.
Эквивалента им в собираемом наборе нет — ``tests/sources/`` проверяет сам
``core.backend_installers``, а не мост к нему, — так что это был не
дубль, а пропавшее покрытие.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from PySide6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backend_installers import BACKENDS, BackendId  # noqa: E402
from ui.models.model_registry import ModelRegistry, _format_size  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QGuiApplication:
    # QSettings внутри ModelRegistry требует QCoreApplication;
    # QGuiApplication — его наследник.
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    created = QGuiApplication(sys.argv or [""])
    created.setApplicationName("model-registry-test")
    created.setOrganizationName("model-registry-test")
    return created


@pytest.fixture()
def registry(app: QGuiApplication) -> ModelRegistry:
    return ModelRegistry()


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (0, "—"),
        (-1, "—"),
        (420_000_000, "420 MB"),
        # Границы веток самого форматтера: MB до 1000, дробная GB до 10,
        # целая GB выше. Ровно на стыке проверяется потому, что именно
        # там ошибаются на единицу.
        (999_000_000, "999 MB"),
        (1_000_000_000, "1.0 GB"),
        (3_100_000_000, "3.1 GB"),
        (9_900_000_000, "9.9 GB"),
        (10_000_000_000, "10 GB"),
        (15_000_000_000, "15 GB"),
    ],
)
def test_format_size(size_bytes, expected):
    assert _format_size(size_bytes) == expected


def test_row_count_matches_backends(registry: ModelRegistry):
    """Реестр показывает ровно те бэкенды, что объявлены в core."""
    assert registry.rowCount() == len(BACKENDS)
    assert registry.rowCount() > 0, "BACKENDS пуст — проверка ниже стала бы пустой"


def test_every_row_is_a_known_backend(registry: ModelRegistry):
    known = {b.value for b in BackendId}
    for row in range(registry.rowCount()):
        entry = registry.entryAt(row)
        assert entry is not None, f"entryAt({row}) вернул None"
        assert entry["backend_id"] in known, f"неизвестный backend_id {entry['backend_id']!r}"
        assert isinstance(entry["name"], str) and entry["name"]
        assert isinstance(entry["installed"], bool)
        assert isinstance(entry["active"], bool)


def test_entry_at_rejects_out_of_range(registry: ModelRegistry):
    assert registry.entryAt(-1) is None
    assert registry.entryAt(registry.rowCount()) is None


def test_at_most_one_row_is_active(registry: ModelRegistry):
    actives = [r for r in range(registry.rowCount()) if registry.entryAt(r)["active"]]
    assert len(actives) <= 1, f"активных строк {len(actives)}, ожидалось не больше одной"


def test_set_active_refuses_an_uninstalled_backend(registry: ModelRegistry):
    """``setActive`` на неустановленном бэкенде — отказ, а не пометка.

    Экран не должен уметь сделать активным то, чего нет на диске:
    пайплайн пошёл бы в отсутствующие веса.
    """
    uninstalled = [
        r for r in range(registry.rowCount()) if not registry.entryAt(r)["installed"]
    ]
    if not uninstalled:
        pytest.skip("в этом окружении установлены все бэкенды — отказ проверить не на чем")

    row = uninstalled[0]
    registry.setActive(row)

    assert registry.entryAt(row)["active"] is False, (
        f"строка {row} стала активной, хотя бэкенд не установлен"
    )
