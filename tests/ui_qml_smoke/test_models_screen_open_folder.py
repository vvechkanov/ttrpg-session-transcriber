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

Both tests run the production path rather than a model of it:

* the install goes through the public ``ModelRegistry.install`` and the
  real ``InstallWorker`` on its real ``QThread``, with only the network
  download (``install_backend``) stubbed, so the test still fails if
  ``install`` stops starting a worker or ``done`` stops being connected;
* the click goes through the button's own ``onClicked``, with the
  ``file`` scheme intercepted via ``QDesktopServices.setUrlHandler`` so
  the assertion reads the URL the app actually asked to open instead of
  a file manager opening on the CI runner.

The second one is what catches a half-finished migration: a leftover
``modelsRoot()`` call parses fine and only raises ``TypeError`` when the
handler runs, which is the moment this test reproduces.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.pipeline import run as _warm  # noqa: F401

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle

from core.backend_installers import BackendId, models_root_path
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


@pytest.fixture
def screen(tmp_path_factory):
    """ModelsScreen loaded against an empty, throwaway models home.

    Per test, not per module: both tests below care about the state of
    the models directory, and one of them creates it. Sharing the
    fixture would make the "nothing installed yet" assertion depend on
    running first — green only while pytest keeps declaration order, and
    invisible when it stops.
    """

    home = tmp_path_factory.mktemp("models-home")
    saved = {key: os.environ.get(key) for key in _ROOT_ENV_KEYS}

    # Everything that can raise lives inside the try, including the
    # engine load: `assert roots` fires exactly when someone has broken
    # ModelsScreen.qml, and leaking a deleted tmpdir as the data home in
    # that moment turns one broken QML line into a cascade of unrelated
    # failures further down the run.
    try:
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


def _pump(app, predicate, timeout_ms: int = 10_000) -> bool:
    """Spin the event loop until ``predicate`` holds or time runs out."""

    from PySide6.QtCore import QElapsedTimer

    clock = QElapsedTimer()
    clock.start()
    while clock.elapsed() < timeout_ms:
        app.processEvents()
        if predicate():
            return True
    return False


class _UrlSink(QObject):
    """Catches what the app asked the desktop to open."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[QUrl] = []

    @Slot(QUrl)
    def handle(self, url: QUrl) -> None:
        self.urls.append(url)


@pytest.mark.gui
def test_install_wakes_the_button_without_rebuilding_it(screen, monkeypatch):
    """The regression: the binding latched ``False`` at creation time.

    Both halves live in one test on purpose — "disabled while there is
    no folder" and "enabled after the install" are two ends of one
    transition, and asserting them apart would only re-create the
    ordering dependency the per-test fixture exists to remove.
    """
    root, registry, app = screen

    button = _button(root)  # held across the install on purpose
    assert not models_root_path().exists()
    assert button.property("enabled") is False, "nothing installed, nothing to open"

    # The only thing stubbed is the several-hundred-megabyte download.
    # Everything downstream of it is the app's own: install() → QThread →
    # InstallWorker.run → done → _on_worker_done → installedStateChanged.
    asked_for: list[BackendId] = []

    def fake_install_backend(backend_id, progress=None):
        asked_for.append(backend_id)
        (models_root_path() / "gigaam").mkdir(parents=True, exist_ok=True)
        if progress is not None:
            progress(1.0, "готово")

    monkeypatch.setattr(
        "ui.engines.install_worker.install_backend", fake_install_backend
    )

    finished: list[int] = []
    registry.installFinished.connect(finished.append)

    row = 0
    assert registry.entryAt(row) is not None
    registry.install(row)

    assert _pump(app, lambda: bool(finished)), "install never reported finishing"
    assert asked_for, "install() did not reach the installer through the worker"

    assert button.property("enabled") is True, (
        "the button held the value it had at component creation — "
        "a binding over a plain Slot never re-evaluates"
    )


@pytest.mark.gui
def test_clicking_asks_the_desktop_to_open_the_models_folder(screen):
    """Runs the real ``onClicked``, so a stale ``modelsRoot()`` call fails.

    A leftover call site parses fine and raises ``TypeError`` only when
    the handler runs; then nothing is opened and ``urls`` stays empty.
    """
    root, registry, app = screen

    (models_root_path() / "gigaam").mkdir(parents=True, exist_ok=True)
    registry.refresh()
    app.processEvents()

    button = _button(root)
    assert button.property("enabled") is True

    sink = _UrlSink()
    QDesktopServices.setUrlHandler("file", sink, "handle")
    try:
        button.metaObject().invokeMethod(button, "clicked")
        app.processEvents()
    finally:
        QDesktopServices.unsetUrlHandler("file")

    assert len(sink.urls) == 1, (
        "the click opened nothing — a leftover modelsRoot() call raises "
        "TypeError inside onClicked and swallows the whole handler"
    )
    assert Path(sink.urls[0].toLocalFile()) == models_root_path()
