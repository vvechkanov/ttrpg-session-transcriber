"""Smoke test: "Открыть папку моделей" wakes up once a model is installed.

The button is disabled while the models directory does not exist — on a
fresh install there is nothing to open. The bug was that it stayed
disabled *forever*: ``enabled`` was bound to ``modelRegistry.modelsRoot()``,
a plain ``Slot``, and a QML binding over a plain method is evaluated once
at component creation and never again. Installing a model created the
directory and changed nothing on screen until the app was restarted.

The same trap is documented twice elsewhere in the project —
``ui/models/session.py`` (``count``/``activeCount``) and
``ui/qml/screens/TimelineScreen.qml`` — where a header froze at "0 из 0".

The second test holds on to the *same* QQuickItem across the install, so
it fails if the value only ever refreshes by rebuilding the component.
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

from core.backend_installers import models_root_path
from ui.models import AppModel, AppPreferences, ModelRegistry

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QML_ROOT = _PROJECT_ROOT / "ui" / "qml"
_MODELS_QML = _QML_ROOT / "screens" / "ModelsScreen.qml"

# Both are read on every call to ``default_models_root``: XDG_DATA_HOME on
# Linux/macOS, APPDATA on Windows. Setting both keeps the test honest on
# the whole CI matrix instead of only on the runner that happens to be
# POSIX.
_ROOT_ENV_KEYS = ("XDG_DATA_HOME", "APPDATA")

_ALIVE: list = []


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("models-folder-test")
    app.setOrganizationName("models-folder-test")
    return app


@pytest.fixture(scope="module")
def screen(tmp_path_factory):
    """ModelsScreen loaded against an empty, throwaway models home."""

    home = tmp_path_factory.mktemp("models-home")
    saved = {key: os.environ.get(key) for key in _ROOT_ENV_KEYS}
    for key in _ROOT_ENV_KEYS:
        os.environ[key] = str(home)

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
    try:
        yield roots[0], registry, app
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _button(root) -> QQuickItem:
    found = root.findChild(QQuickItem, "openModelsFolder")
    assert found is not None, "«Открыть папку моделей» not found by objectName"
    return found


@pytest.mark.gui
def test_button_is_disabled_while_there_is_no_folder(screen):
    """First run: nothing installed, nothing to open."""
    _root, _registry, _app = screen

    assert not models_root_path().exists()
    assert _button(_root).property("enabled") is False


@pytest.mark.gui
def test_install_wakes_the_button_without_rebuilding_it(screen):
    """The regression: the binding latched ``False`` at creation time."""
    root, registry, app = screen

    button = _button(root)  # held across the install on purpose
    assert button.property("enabled") is False

    (models_root_path() / "gigaam").mkdir(parents=True)
    # The slot ``InstallWorker.done`` is wired to in ``_start_worker`` —
    # driving it here exercises the real completion path (rebuild plus
    # ``installedStateChanged``) rather than a signal invented by the test.
    registry._on_worker_done("gigaam-rnnt-fp32")
    app.processEvents()

    assert button.property("enabled") is True, (
        "the button held the value it had at component creation — "
        "a binding over a plain Slot never re-evaluates"
    )


def test_qml_reads_the_models_root_as_a_property_everywhere():
    """Guard against a half-finished migration.

    ``modelsRoot`` is a notifying ``Property``. A leftover ``modelsRoot()``
    call site would keep parsing and only blow up as a runtime TypeError
    the moment the user clicks — which no test above would reach, because
    clicking opens a file manager.

    ``//`` comments are stripped first: a guard that trips over the
    sentence explaining it is a guard nobody keeps.
    """

    text = "\n".join(
        line.split("//", 1)[0]
        for line in _MODELS_QML.read_text(encoding="utf-8").splitlines()
    )
    assert "modelsRoot()" not in text, (
        "modelsRoot is a Property, not a method: calling it raises "
        "'modelsRoot is not a function' at click time"
    )
