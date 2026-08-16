"""Smoke test: a failed model install says why.

``ModelRegistry.installFailed`` is the only channel telling the user
that a several-hundred-megabyte download died — dead network, full
disk, corrupt archive. The handler accepted the message and dropped it,
so the whole event looked like the progress bar quietly disappearing.

This is also the screen the "no model installed" banner sends people
to, which makes a silence here the most expensive one in the app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.pipeline import run as _warm  # noqa: F401

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle

from ui.models import AppModel, AppPreferences, ModelRegistry

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QML_ROOT = _PROJECT_ROOT / "ui" / "qml"
_MODELS_QML = _QML_ROOT / "screens" / "ModelsScreen.qml"

_ALIVE: list = []


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("models-error-test")
    app.setOrganizationName("models-error-test")
    return app


@pytest.fixture(scope="module")
def screen():
    app = _ensure_app()
    QQuickStyle.setStyle("Basic")
    qmlRegisterSingletonType(
        QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml")), "App.Theme", 1, 0, "Theme"
    )

    registry = ModelRegistry()
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(_QML_ROOT))
    ctx = engine.rootContext()
    ctx.setContextProperty("appModel", AppModel())
    ctx.setContextProperty("preferences", AppPreferences())
    ctx.setContextProperty("modelRegistry", registry)
    engine.load(QUrl.fromLocalFile(str(_MODELS_QML)))

    roots = engine.rootObjects()
    assert roots, "ModelsScreen.qml failed to parse"
    _ALIVE.append((engine, registry))
    yield roots[0], registry, app


def _strip(root) -> QQuickItem:
    found = root.findChild(QQuickItem, "installError")
    assert found is not None, "installError strip not found by objectName"
    return found


@pytest.mark.gui
def test_strip_is_hidden_until_something_fails(screen):
    root, _registry, _app = screen
    assert _strip(root).property("visible") is False


@pytest.mark.gui
def test_failed_install_shows_the_reason(screen):
    """The regression: the message was accepted and thrown away."""
    root, registry, app = screen

    registry.installFailed.emit(0, "Нет соединения с сервером моделей.")
    app.processEvents()

    strip = _strip(root)
    assert strip.property("visible") is True
    assert strip.property("text") == "Нет соединения с сервером моделей."


@pytest.mark.gui
def test_empty_reason_still_says_something(screen):
    """A blank message must not produce a blank banner."""
    root, registry, app = screen

    _strip(root).setProperty("text", "")
    registry.installFailed.emit(0, "")
    app.processEvents()

    strip = _strip(root)
    assert strip.property("visible") is True
    assert strip.property("text"), "an empty failure still needs a sentence"


@pytest.mark.gui
def test_starting_a_new_install_clears_the_old_error(screen):
    """Retrying must not leave the previous failure on screen."""
    root, registry, app = screen

    registry.installFailed.emit(0, "Диск переполнен.")
    app.processEvents()
    assert _strip(root).property("visible") is True

    # Same path the row's Install button takes.
    _strip(root).setProperty("text", "")
    app.processEvents()
    assert _strip(root).property("visible") is False
