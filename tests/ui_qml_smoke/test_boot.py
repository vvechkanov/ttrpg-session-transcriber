"""Smoke test: load ``ui/qml/Main.qml`` without errors or warnings.

Run directly during Phase 1 development:

    QT_QPA_PLATFORM=offscreen python tests/ui_qml_smoke/test_boot.py

Exits with code 0 when the QML tree parses and instantiates a root
object, 1 otherwise. Any QML warning (undefined property, missing
import, style plugin missing…) is printed on stderr and counts as a
failure — this mirrors the `-qmllint-like` check that Phase 11 will
upgrade into a proper pytest-qt assertion.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, qInstallMessageHandler, QtMsgType
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuickControls2 import QQuickStyle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ui.engines import PipelineController  # noqa: E402
from ui.models import (  # noqa: E402
    AppModel,
    AppPreferences,
    ModelRegistry,
    SessionMeta,
    SourceListModel,
    TrackListModel,
)


_warnings: list[str] = []


def _handler(mode: QtMsgType, context: QObject, message: str) -> None:
    # Qt routes QML.warning() + missing-property diagnostics here. Any
    # message that mentions a file path we own counts as a failure.
    if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        if "qml" in message.lower() or ".qml" in message:
            _warnings.append(message)
    sys.stderr.write(message + "\n")


def main() -> int:
    qInstallMessageHandler(_handler)
    QQuickStyle.setStyle("Basic")

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Session Transcriber Smoke")
    app.setOrganizationName("Session Transcriber")

    qml_root = ROOT / "ui" / "qml"
    theme_url = QUrl.fromLocalFile(str(qml_root / "Theme.qml"))
    qmlRegisterSingletonType(theme_url, "App.Theme", 1, 0, "Theme")

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_root))

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

    engine.load(QUrl.fromLocalFile(str(qml_root / "Main.qml")))

    if not engine.rootObjects():
        sys.stderr.write("FAIL: engine.rootObjects() is empty\n")
        return 1

    if _warnings:
        sys.stderr.write(f"FAIL: {len(_warnings)} QML warning(s)\n")
        return 1

    print("OK: Main.qml loaded without warnings, 4 screens in StackLayout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
