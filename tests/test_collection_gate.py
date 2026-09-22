"""Сторож сбора: файл, названный тестом, обязан давать хоть один тест.

Четыре файла в ``tests/ui_qml_smoke/`` лежали в ``testpaths``, назывались
``test_*.py`` и не давали pytest ни одной проверки: внутри был ``main()``
и вызов под ``if __name__ == "__main__"``. Со стороны это неотличимо от
покрытия — файл виден в дереве, его имя попадает в отчёты, — а на деле CI
их не исполнял и молчал об этом. В один из них (``test_app_preferences``)
починка по замечанию ревью дописала ещё и функцию ``_renderer_round_trip``
с настоящими ``assert``, которую не звал никто: мёртвая проверка внутри
мёртвого файла.

Сторож смотрит на ФАКТИЧЕСКИЙ сбор pytest, а не на разбор исходника через
``ast``. Разница существенна: тест может приходить из ``parametrize``, из
генерации в ``conftest``, из базового класса в другом модуле — и любой
разбор «есть ли в файле ``def test_``» однажды соврёт в обе стороны.
Единственный, кто знает правду о сборе, — сам pytest, поэтому он и
спрашивается, отдельным процессом.

Отдельный процесс, а не ``pytest.main`` в этом же: ``--collect-only``
импортирует весь набор, включая этот модуль, и повторный вход в уже
работающий pytest даёт либо рекурсию, либо порчу его глобального
состояния.

ГРАНИЦА КОНТРАКТА, замеренная и намеренно оставленная. Сторож требует
«хотя бы один СОБРАННЫЙ тест», а не «хотя бы одна исполнившаяся
проверка», и это две разные вещи. Файл, где все тесты — пустой
``@pytest.mark.parametrize("x", [])``, сторожа пройдёт: pytest 9.1.1
собирает из такого один узел ``test_x[NOTSET]`` и помечает его
``skipped`` при прогоне. То есть ``assert`` не исполнится ни один, а
сторож останется зелёным. Расширять его до «файл обязан что-то реально
проверять» здесь не стали: это уже не про сбор, и мерить пришлось бы
исполнение, а не список узлов.

Заодно эта же граница зависит от версии pytest, а не гарантирована:
пустой ``parametrize`` — деталь реализации. На pytest, который отдавал
бы здесь ноль узлов, сторож бы покраснел, и это было бы верно.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_ROOT.parent


def _collected_files() -> set[str]:
    """Пути файлов, из которых pytest собрал хотя бы один тест.

    Возвращает пути в posix-написании относительно корня проекта — в том
    же виде, в каком pytest печатает node id, чтобы сравнение не зависело
    от разделителя платформы.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "--collect-only",
            "-q",
            # Свой addopts (`-v`) сделал бы вывод деревом вместо node id.
            "-o",
            "addopts=",
            # Кеш не нужен и в песочнице CI может быть недоступен на запись.
            "-p",
            "no:cacheprovider",
        ],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        # Сбор — единицы секунд (замер: 0.39 с на 970 тестов). Без
        # таймаута импорт, ушедший в сеть или в ожидание устройства,
        # вешает не этот тест, а весь прогон CI, и без вывода: причину
        # тогда не видно вовсе.
        timeout=300,
    )
    # Код выхода 0 (собралось) или 5 (не собралось ничего). Всё
    # остальное — ошибка сбора, и тогда сторож молчать не должен: пустой
    # список файлов он иначе объявит «все файлы пусты».
    if proc.returncode not in (0, 5):
        pytest.fail(
            "pytest --collect-only завершился с кодом "
            f"{proc.returncode}; собрать набор не удалось:\n"
            f"{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
        )

    files: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "::" not in line:
            continue
        path = line.split("::", 1)[0]
        if path.endswith(".py"):
            files.add(path.replace("\\", "/"))
    return files


def _test_modules() -> set[str]:
    """Файлы ``test_*.py`` под ``tests/``, которые pytest обязан собрать."""
    found: set[str] = set()
    for path in _TESTS_ROOT.rglob("test_*.py"):
        if "__pycache__" in path.parts:
            continue
        found.add(path.relative_to(_PROJECT_ROOT).as_posix())
    return found


def test_every_test_file_yields_at_least_one_test():
    modules = _test_modules()
    assert modules, "под tests/ не нашлось ни одного файла test_*.py — сломан сам сторож"

    collected = _collected_files()
    assert collected, "pytest не собрал ни одного теста — сломан сам сторож"

    empty = sorted(modules - collected)
    assert not empty, (
        "Файлы названы тестами, но pytest не собрал из них ни одной проверки.\n"
        "Либо в них есть что проверять — тогда это pytest-тесты, а не main(),\n"
        "либо проверять нечего — тогда файл честнее удалить, чем оставлять\n"
        "видимость покрытия:\n  " + "\n  ".join(empty)
    )
