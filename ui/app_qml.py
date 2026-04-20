"""Entry point for the new PySide6 + QML shell (ADR: QML migration).

Run:
    python -m ui.app_qml

This host is independent of the legacy QWidgets shell in
:mod:`ui.shell.app`. Wiring it into ``ui.main()`` happens only after
the QML shell reaches feature parity — keeping two entry points lets
us iterate on QML without regressing the shipping GUI.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuickControls2 import QQuickStyle

from ui.models import AppModel, ModelRegistry


_QML_ROOT = Path(__file__).resolve().parent / "qml"


def _register_theme_singleton() -> None:
    """Expose ``Theme.qml`` as ``import App.Theme`` in QML.

    Using ``qmlRegisterSingletonType`` with a URL is simpler than the
    alternative (a ``qmldir`` file in a mirrored ``App/Theme/`` tree)
    and keeps the on-disk layout flat.
    """

    theme_url = QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml"))
    qmlRegisterSingletonType(theme_url, "App.Theme", 1, 0, "Theme")


def main() -> int:
    # The warm parchment palette fights Material/Fusion, so stay on
    # Basic and style each control ourselves — same call the QML
    # mapping doc recommends.
    QQuickStyle.setStyle("Basic")

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Session Transcriber")
    app.setOrganizationName("Session Transcriber")

    _register_theme_singleton()

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(_QML_ROOT))

    app_model = AppModel()
    model_registry = ModelRegistry()
    engine.rootContext().setContextProperty("appModel", app_model)
    engine.rootContext().setContextProperty("modelRegistry", model_registry)

    engine.load(QUrl.fromLocalFile(str(_QML_ROOT / "Main.qml")))
    if not engine.rootObjects():
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
