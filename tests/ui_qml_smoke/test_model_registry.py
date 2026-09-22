"""``ModelRegistry`` — мост между ``core.backend_installers`` и экраном моделей.

Файл был скриптом с ``main()`` и ручными ``_assert``: pytest собирал из
него ноль тестов, то есть ни одна проверка ниже в CI не исполнялась.

Говорить, что мост ``ModelRegistry`` ↔ ``core.backend_installers`` не
проверял никто, было бы неправдой, и проверено это грепом:
``tests/ui_qml_smoke/test_models_screen_open_folder.py`` и
``test_models_screen_install_error.py`` строят настоящий реестр и
доходят до живого ``InstallWorker`` — глубже, чем этот файл. Чего в
собираемом наборе не было вовсе: ``_format_size``, равенство
``rowCount()`` и ``len(BACKENDS)``, проверки формы строки в ``entryAt``
и отказ ``setActive`` на неустановленном бэкенде.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.backend_installers import BACKENDS, BackendId  # noqa: E402
from ui.models.model_registry import (  # noqa: E402
    _BACKEND_TO_ASR_ID,
    ModelRegistry,
    _format_size,
)


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
def registry(app: QGuiApplication, tmp_path: Path) -> ModelRegistry:
    """Реестр поверх собственного INI.

    ``ModelRegistry.setActive`` пишет выбранный бэкенд в QSettings, и
    тест отказа ниже проверяет, что при отказе запись НЕ случилась.
    Без своего каталога такая проверка читала бы настоящий INI
    разработчика — и портила бы его, случись отказ сломанным.
    """
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    try:
        yield ModelRegistry()
    finally:
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.TempLocation
            ),
        )


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (0, "—"),
        (-1, "—"),
        (420_000_000, "420 MB"),
        # Границы веток самого форматтера: MB до 1000, дробная GB до 10,
        # целая GB выше.
        #
        # НАСТОЯЩИЙ СТЫК ВЕТКИ MB ЗДЕСЬ НЕ ПРОВЕРЯЕТСЯ, и это сказано
        # прямо, чтобы список не выглядел исчерпывающим. Ветка выбирается
        # по `mb < 1000`, а печатается `int(round(mb))`, поэтому на
        # 999_500_000 форматтер отдаёт "1000 MB" — мегабайты там, где по
        # замыслу уже гигабайты. Замерено; это дефект самого форматтера,
        # заведён отдельной карточкой, а не починен здесь: карточка
        # ночи — про мёртвые файлы тестов, и правка продакшна в неё не
        # входит. Кейс с ожиданием "1000 MB" не добавлен намеренно —
        # он закрепил бы дефект как норму.
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

    ПРОВЕРЯЕТСЯ ЗДЕСЬ НЕ ФЛАГ ``active``, И ЭТО СУТЬ ТЕСТА. Флаг для
    неустановленных строк независимо гасит ``_build_rows``
    («Only keep the active flag on a row that's actually installed»),
    который зовётся из ``setActive`` через ``_rebuild_and_reset``.
    То есть флаг уезжает в ``False`` и когда отказ сработал, и когда
    его сняли, — проверка по нему меряет чужой механизм и защиту не
    видит вовсе. Мутационная проверка это и показала: снятие условия
    ``if not target.installed`` пережило весь набор из 1026 тестов.

    Настоящее последствие — ``activeModelId``: его читает пайплайн,
    когда у дорожки нет своего override, и именно он подменялся на
    неустановленный бэкенд, да ещё и уезжал в QSettings.
    """
    active_now = registry.activeModelId

    # Нужна строка, которая при снятой защите РЕАЛЬНО подменила бы
    # activeModelId. Неустановленная строка с тем же asr id, что уже
    # активен, дала бы no-op, и тест был бы зелёным ни от чего.
    candidates = [
        r
        for r in range(registry.rowCount())
        if not registry.entryAt(r)["installed"]
        and _BACKEND_TO_ASR_ID.get(BackendId(registry.entryAt(r)["backend_id"]))
        not in (None, active_now)
    ]
    if not candidates:
        pytest.skip(
            "нет неустановленного бэкенда, отличного от активного — "
            "отказ проверить не на чем"
        )

    row = candidates[0]
    registry.setActive(row)

    assert registry.activeModelId == active_now, (
        f"setActive({row}) подменил активную модель на неустановленный "
        f"бэкенд: {active_now!r} → {registry.activeModelId!r}"
    )
    # Второй экземпляр читает QSettings заново — так видно, дошёл ли
    # отказ до диска или только до памяти.
    assert ModelRegistry().activeModelId == active_now, (
        f"setActive({row}) записал неустановленный бэкенд в QSettings"
    )
    assert registry.entryAt(row)["active"] is False
