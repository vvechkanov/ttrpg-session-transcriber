"""Экран настроек не обещает того, чего приложение не делает.

Шесть контролов на этом экране честно писали значение в QSettings, и
никто его не читал: рабочая папка, язык интерфейса, подсказки, звук по
завершении, режим OOC. Пользователь двигал их и ничего не менялось —
причём молча, что хуже неработающей кнопки: кнопка хотя бы не врёт про
результат.

Решение по карточке — вариант «б»: контролы остаются на экране, чтобы
было видно, куда идёт проект, но выключаются и помечаются «скоро».

Проверки идут по свойству ``enabled`` смонтированного дерева, а не по
исходнику QML: ``enabled`` наследуется вниз, и только чтение с живого
элемента отвечает на вопрос «сможет ли пользователь это тронуть».
Отдельно проверяется обратное — что рабочие настройки остались
доступными, иначе «выключить всё» прошло бы как успех.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Прогреваем sources/__init__ до глубоких импортов Qt (см. test_core_asr).
from core.pipeline import run as _  # noqa: F401

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import qmlRegisterSingletonType
from PySide6.QtQuick import QQuickItem, QQuickView
from PySide6.QtQuickControls2 import QQuickStyle

from ui.engines import PipelineController
from ui.models import (
    AppModel,
    AppPreferences,
    ModelRegistry,
    SessionMeta,
    SourceListModel,
    TrackListModel,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QML_ROOT = _PROJECT_ROOT / "ui" / "qml"
_SETTINGS_QML = _QML_ROOT / "screens" / "SettingsScreen.qml"

#: Заголовки групп, за которыми не стоит ни одного читателя настройки.
#: Проверено grep-ом по всему дереву: ни `paths/working_folder`, ни
#: `interface/*` не читает никто, а QTranslator в проекте отсутствует.
SOON_GROUPS = ("Рабочая папка", "Интерфейс")

#: То же на уровне отдельного поля: OOC живёт внутри рабочей группы
#: «Мержер по умолчанию», поэтому выключается сам, а не вся группа.
SOON_FIELDS = ("OOC В FOUNDRY-ЧАТЕ",)

#: Обратная сторона: эти доезжают до пайплайна и обязаны остаться
#: доступными. Если однажды выключат и их, проверка выше промолчит.
WORKING_GROUPS = ("ASR (распознавание речи)", "Чанки для LLM", "Мержер по умолчанию")
WORKING_FIELDS = ("МАКС. GAP МЕЖДУ РЕПЛИКАМИ", "ФОРМАТ merged.txt")


@dataclass
class _Harness:
    """Контекстные объекты надо держать живыми всё время теста.

    ``setContextProperty`` не забирает владение и не назначает родителя,
    так что выход локальных переменных из области видимости убивает
    C++-сторону под живым деревом QML.
    """

    app: QGuiApplication
    view: QQuickView
    root: QQuickItem
    context_objects: tuple[Any, ...]


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("settings-promises-test")
    app.setOrganizationName("settings-promises-test")
    return app


@pytest.fixture(scope="module")
def screen() -> _Harness:
    app = _ensure_app()
    QQuickStyle.setStyle("Basic")
    theme_url = QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml"))
    qmlRegisterSingletonType(theme_url, "App.Theme", 1, 0, "Theme")

    app_model = AppModel()
    tracks_model = TrackListModel()
    sources_model = SourceListModel()
    session_meta = SessionMeta()
    pipeline = PipelineController(app_model, tracks_model, session_meta)
    preferences = AppPreferences()
    model_registry = ModelRegistry()

    view = QQuickView()
    view.engine().addImportPath(str(_QML_ROOT))
    ctx = view.rootContext()
    ctx.setContextProperty("appModel", app_model)
    ctx.setContextProperty("preferences", preferences)
    ctx.setContextProperty("modelRegistry", model_registry)
    ctx.setContextProperty("tracksModel", tracks_model)
    ctx.setContextProperty("sourcesModel", sources_model)
    ctx.setContextProperty("sessionMeta", session_meta)
    ctx.setContextProperty("pipeline", pipeline)

    view.setSource(QUrl.fromLocalFile(str(_SETTINGS_QML)))
    assert view.status() != QQuickView.Status.Error, [
        e.toString() for e in view.errors()
    ]

    view.resize(1280, 900)
    view.show()
    app.processEvents()

    root = view.rootObject()
    assert root is not None, "SettingsScreen.qml не загрузился"

    return _Harness(
        app=app,
        view=view,
        root=root,
        context_objects=(
            app_model,
            tracks_model,
            sources_model,
            session_meta,
            pipeline,
            preferences,
            model_registry,
        ),
    )


def _walk(item: QQuickItem):
    """Всё дерево элементов вглубь.

    Именно visual-дерево, а не ``findChildren``: элементы, созданные
    ``Repeater``/``Loader``, принадлежат своему QML-контексту, а не
    QObject-родителю, и рекурсивный поиск по QObject их не находит.
    """

    yield item
    for child in item.childItems():
        yield from _walk(child)


#: Текст плашки, которой помечены невыполненные настройки.
SOON_BADGE = "СКОРО"


def _by_property(root: QQuickItem, name: str, value: str) -> QQuickItem | None:
    """Единственный элемент с таким значением свойства.

    Именно единственный. На экране уже есть два поля с меткой «ЯЗЫК» —
    рабочее в группе ASR и мёртвое в «Интерфейсе», — и поиск «первый
    подошедший» однажды начнёт сторожить не то поле, о чём никто не
    узнает. Неоднозначность обязана падать, а не разрешаться порядком
    обхода дерева.
    """

    found = [item for item in _walk(root) if item.property(name) == value]
    assert len(found) <= 1, (
        f"на экране {len(found)} элементов с {name}={value!r} — "
        f"проверка не может знать, о котором из них речь"
    )
    return found[0] if found else None


def _own_subtree(item: QQuickItem):
    """Поддерево элемента без вложенных владельцев пометки.

    Плашка принадлежит ближайшему предку, у которого есть свойство
    ``soon``. Без этого разделения рабочая группа «Мержер по умолчанию»
    считалась бы помеченной: внутри неё лежит помеченное поле OOC, и
    поиск по всему поддереву нашёл бы его плашку.
    """

    yield item
    for child in item.childItems():
        if child.property("soon") is not None:
            continue  # у него своя пометка, чужую он не наследует
        yield from _own_subtree(child)


def _has_visible_badge(item: QQuickItem) -> bool:
    """Видит ли пользователь плашку «СКОРО» на самом этом элементе."""

    return any(
        child.property("text") == SOON_BADGE and child.isVisible()
        for child in _own_subtree(item)
    )


def _group(root: QQuickItem, title: str) -> QQuickItem:
    found = _by_property(root, "title", title)
    assert found is not None, (
        f"группа настроек {title!r} не найдена на экране — "
        f"её переименовали или убрали, и эта проверка больше ничего не сторожит"
    )
    return found


def _field(root: QQuickItem, label: str) -> QQuickItem:
    found = _by_property(root, "label", label)
    assert found is not None, (
        f"поле настроек {label!r} не найдено на экране — "
        f"его переименовали или убрали"
    )
    return found


@pytest.mark.parametrize("title", SOON_GROUPS)
def test_unimplemented_groups_are_disabled(screen: _Harness, title: str) -> None:
    """Группа без единого читателя не должна принимать ввод."""

    group = _group(screen.root, title)
    assert group.isEnabled() is False, (
        f"группа {title!r} принимает ввод, хотя её значения никто не читает: "
        f"пользователь меняет настройку и ничего не происходит"
    )


@pytest.mark.parametrize("title", SOON_GROUPS)
def test_unimplemented_groups_say_they_are_coming(screen: _Harness, title: str) -> None:
    """Выключенного мало — нужно сказать, почему.

    Серый контрол без объяснения читается как поломка. Пометка «скоро»
    отличает «ещё не сделано» от «сломалось».
    """

    group = _group(screen.root, title)
    assert _has_visible_badge(group), (
        f"группа {title!r} выключена, но плашки «{SOON_BADGE}» на ней не видно — "
        f"выглядит как сломавшийся интерфейс, а не как планы. "
        f"Проверяется именно видимый потомок: флага `soon` мало, его "
        f"можно оставить, а плашку вырезать, и пользователь этого не узнает"
    )


@pytest.mark.parametrize("label", SOON_FIELDS)
def test_unimplemented_fields_are_disabled_and_marked(
    screen: _Harness, label: str
) -> None:
    """OOC — не проводка, а несделанная фича, и помечается как фича.

    В пайплайне нет параметра OOC вовсе: у ``ScriptMerger`` единственный
    аргумент — ``gap_sec``, канал не влияет ни на один рендерер (это
    заморожено в ``tests/test_renderers.py``), а источник FVTT всегда
    проставляет ``"ic"``. Довести настройку «до пайплайна» здесь не
    к чему — значит она в одном ряду с языком и звуком.
    """

    field = _field(screen.root, label)
    assert field.isEnabled() is False, f"поле {label!r} принимает ввод в никуда"
    assert _has_visible_badge(field), (
        f"на поле {label!r} не видно плашки «{SOON_BADGE}»"
    )


@pytest.mark.parametrize("title", WORKING_GROUPS)
def test_working_groups_stay_available(screen: _Harness, title: str) -> None:
    """Обратная сторона: рабочие настройки нельзя выключить заодно.

    Без этой проверки «выключить всё подряд» прошло бы как успех.
    """

    group = _group(screen.root, title)
    assert group.isEnabled() is True, f"рабочая группа {title!r} выключена"
    assert not _has_visible_badge(group), f"рабочая группа {title!r} помечена «{SOON_BADGE}»"


@pytest.mark.parametrize("label", WORKING_FIELDS)
def test_working_fields_stay_available(screen: _Harness, label: str) -> None:
    field = _field(screen.root, label)
    assert field.isEnabled() is True, f"рабочее поле {label!r} выключено"
    assert not _has_visible_badge(field), f"рабочее поле {label!r} помечено «{SOON_BADGE}»"
