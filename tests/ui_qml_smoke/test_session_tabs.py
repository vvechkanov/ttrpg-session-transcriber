"""Smoke test: the four session tabs say the truth about themselves.

``SessionTopBar`` draws four tabs — Обработка / Транскрипт / Журнал /
Настройки сессии. Three of them lead to screens that do not exist yet.

The decision on the card (option «в») is: keep all four, so the tabs go
on showing where the project is heading, but disable the three that are
not ready instead of letting them look clickable and do nothing.

The tests click real tabs in a real window rather than poking
properties. That is deliberate: the defect being fixed was a signal
nobody listened to, and *every* property-level assertion passes just as
happily with the listener deleted — checked by removing
``onTabActivated`` and watching a property-only suite stay green. Only a
tap crosses the same wiring the user does.

What is checked here:

1. All four tabs are still drawn, in order.
2. Exactly one — «Обработка» — is enabled; the other three are not.
3. Tapping the ready tab travels signal → ``TimelineScreen.sessionTab``
   → back down to the bar's underline. This is the wiring the card is
   about.
4. Tapping a disabled tab moves nothing.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Warm sources/__init__ before deep Qt imports.
from core.pipeline import run as _  # noqa: F401

from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import qmlRegisterSingletonType
from PySide6.QtQuick import QQuickItem, QQuickView
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

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
_TIMELINE_QML = _QML_ROOT / "screens" / "TimelineScreen.qml"

#: Order matters: it is the order the user reads them left to right.
_EXPECTED_TABS = ["process", "transcript", "log", "settings"]

#: Only the processing tab has a screen behind it today.
_READY_TABS = {"process"}


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("session-tabs-test")
    app.setOrganizationName("session-tabs-test")
    return app


@dataclass
class _Harness:
    """Everything the mounted screen needs kept alive.

    The context objects have to be held for the lifetime of the test,
    not just of the setup function. ``setContextProperty`` does not take
    ownership and gives them no QObject parent, so letting the locals go
    out of scope deletes the C++ side underneath a live QML tree: the
    bindings then read from null and the screen mounts half-dead,
    spilling ``TypeError: Cannot read property … of null`` for every
    binding that touches ``sessionMeta``.
    """

    app: QGuiApplication
    view: QQuickView
    root: QQuickItem
    context_objects: tuple[Any, ...]


def _mount() -> _Harness:
    """Show TimelineScreen.qml in a window, wired as ``app_qml.py`` does.

    A real ``QQuickView`` rather than a bare ``QQmlApplicationEngine``:
    pointer events need a window to be delivered into, and the point of
    these tests is to press the tabs rather than to set their
    properties.
    """

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

    view.setSource(QUrl.fromLocalFile(str(_TIMELINE_QML)))
    assert view.status() != QQuickView.Status.Error, [
        e.toString() for e in view.errors()
    ]

    view.resize(1280, 800)
    view.show()
    QTest.qWaitForWindowExposed(view)
    app.processEvents()

    root = view.rootObject()
    assert root is not None, "TimelineScreen.qml failed to load"

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


def _tabs(root: QQuickItem) -> list[QQuickItem]:
    """The four tab delegates, left to right.

    Reached through the *visual* tree rather than ``findChildren``:
    items a ``Repeater`` creates belong to their QML context, not to
    the QObject tree under the bar, so a recursive QObject search
    returns nothing at all even while the tabs are on screen.
    """

    row = root.findChild(QObject, "sessionTabRow")
    assert row is not None, "tab row not found — is objectName 'sessionTabRow' set?"

    found = [c for c in row.childItems() if c.objectName() == "sessionTab"]
    assert found, "no tab delegates found — is objectName 'sessionTab' set?"

    # Sorting by x is only meaningful once the layout has run. If it
    # has not, every x is 0, `sorted` quietly falls back to creation
    # order and the ordering assertion below passes without checking
    # anything.
    xs = [item.x() for item in found]
    assert len(set(xs)) == len(xs), f"tabs are not laid out yet: x = {xs}"

    return sorted(found, key=lambda item: item.x())


def _tap(harness: _Harness, tab: QQuickItem) -> None:
    """Click the centre of a tab, the way a user would."""

    centre = tab.mapToScene(QPointF(tab.width() / 2, tab.height() / 2))
    QTest.mouseClick(
        harness.view,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        centre.toPoint(),
    )
    harness.app.processEvents()


@pytest.mark.gui
def test_all_four_tabs_are_still_drawn() -> None:
    """Option «в» keeps the tabs; it does not hide the unfinished ones."""

    harness = _mount()

    ids = [t.property("tabId") for t in _tabs(harness.root)]
    assert ids == _EXPECTED_TABS


@pytest.mark.gui
def test_only_the_ready_tab_is_enabled() -> None:
    """Three tabs lead nowhere, so three tabs must not invite a click."""

    harness = _mount()

    state = {
        t.property("tabId"): bool(t.property("enabled")) for t in _tabs(harness.root)
    }
    assert state == {tab: (tab in _READY_TABS) for tab in _EXPECTED_TABS}


@pytest.mark.gui
def test_tapping_the_ready_tab_is_heard() -> None:
    """The defect itself: ``tabActivated`` had no listener anywhere.

    Deleting ``onTabActivated`` from TimelineScreen.qml must turn this
    test red — it is the only one that crosses the signal.
    """

    harness = _mount()
    bar = harness.root.findChild(QObject, "sessionTopBar")
    assert bar is not None, "SessionTopBar not found — is objectName set?"

    received: list[str] = []
    bar.tabActivated.connect(received.append)

    # Start from somewhere else so "it ended up at process" cannot be
    # satisfied by the default value.
    harness.root.setProperty("sessionTab", "transcript")
    assert bar.property("activeTab") == "transcript"

    process_tab = next(
        t for t in _tabs(harness.root) if t.property("tabId") == "process"
    )
    _tap(harness, process_tab)

    assert received == ["process"], "tapping the ready tab emitted nothing"
    assert harness.root.property("sessionTab") == "process", (
        "SessionTopBar.tabActivated is not wired to TimelineScreen.sessionTab"
    )
    assert bar.property("activeTab") == "process", (
        "SessionTopBar.activeTab is not bound to TimelineScreen.sessionTab"
    )


@pytest.mark.gui
def test_tapping_a_disabled_tab_does_nothing() -> None:
    """A tab that leads nowhere must not move the underline."""

    harness = _mount()
    bar = harness.root.findChild(QObject, "sessionTopBar")
    assert bar is not None

    received: list[str] = []
    bar.tabActivated.connect(received.append)

    for tab in _tabs(harness.root):
        tab_id = tab.property("tabId")
        if tab_id in _READY_TABS:
            continue
        _tap(harness, tab)
        assert received == [], f"disabled tab {tab_id!r} still emitted {received}"
        assert harness.root.property("sessionTab") == "process"
        assert bar.property("activeTab") == "process"
