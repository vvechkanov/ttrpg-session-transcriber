"""Headless boot test — QQmlApplicationEngine loads Main.qml clean.

Spins up the QML loader with all the same context properties the
shipping ``ui/app_qml.py`` registers, then asserts:

1. ``engine.rootObjects()`` is non-empty (the tree parsed).
2. No Qt warnings mentioning ``.qml`` files (missing bindings,
   undefined properties, missing imports) fired during load.

Runs in the default pytest suite with ``QT_QPA_PLATFORM=offscreen``;
also runnable standalone as ``python tests/test_qml_shell_boot.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Headless platform must be set before Qt loads. pytest-qt's own
# fixture respects this; standalone runs also need it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Import core.pipeline first to avoid the sources/__init__ circular
# import seen under the old pipeline_stage_callback test.
from core.pipeline import run as _  # noqa: F401

import pytest

from PySide6.QtCore import QObject, QUrl, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
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

_ROOT = Path(__file__).resolve().parent.parent
_QML_ROOT = _ROOT / "ui" / "qml"


def _app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("Session Transcriber")
    app.setOrganizationName("Session Transcriber")
    return app


@pytest.mark.gui
def test_main_qml_loads_without_warnings():
    app = _app()
    QQuickStyle.setStyle("Basic")

    # Capture QML-layer warnings through a handler; any message that
    # references a .qml file counts as a failure.
    warnings: list[str] = []

    def _handler(mode: QtMsgType, ctx: QObject, message: str) -> None:
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            if "qml" in message.lower() or ".qml" in message:
                warnings.append(message)

    qInstallMessageHandler(_handler)

    try:
        theme_url = QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml"))
        qmlRegisterSingletonType(theme_url, "App.Theme", 1, 0, "Theme")

        engine = QQmlApplicationEngine()
        engine.addImportPath(str(_QML_ROOT))

        app_model = AppModel()
        preferences = AppPreferences()
        model_registry = ModelRegistry()
        tracks_model = TrackListModel()
        sources_model = SourceListModel()
        session_meta = SessionMeta()
        pipeline = PipelineController(app_model, tracks_model, session_meta)

        ctx = engine.rootContext()
        ctx.setContextProperty("appModel", app_model)
        ctx.setContextProperty("preferences", preferences)
        ctx.setContextProperty("modelRegistry", model_registry)
        ctx.setContextProperty("tracksModel", tracks_model)
        ctx.setContextProperty("sourcesModel", sources_model)
        ctx.setContextProperty("sessionMeta", session_meta)
        ctx.setContextProperty("pipeline", pipeline)

        engine.load(QUrl.fromLocalFile(str(_QML_ROOT / "Main.qml")))

        assert engine.rootObjects(), "engine.rootObjects() is empty — Main.qml failed to parse"
        assert not warnings, f"QML warnings during load:\n" + "\n".join(warnings)
    finally:
        # Restore Qt's default handler so subsequent tests don't
        # inherit our failure-capturing one.
        qInstallMessageHandler(None)


if __name__ == "__main__":
    try:
        test_main_qml_loads_without_warnings()
    except AssertionError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        raise SystemExit(1)
    print("OK: Main.qml loaded without warnings, full context registered")
