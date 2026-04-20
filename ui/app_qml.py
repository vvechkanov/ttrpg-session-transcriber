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

from PySide6.QtCore import QObject, QThread, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuickControls2 import QQuickStyle

from ui.engines import PipelineController
from ui.engines.peaks_worker import PeaksWorker
from ui.models import (
    AppModel,
    AppPreferences,
    ModelRegistry,
    SessionMeta,
    SourceListModel,
    TrackListModel,
)


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
    preferences = AppPreferences()
    model_registry = ModelRegistry()
    tracks_model = TrackListModel()
    sources_model = SourceListModel()
    session_meta = SessionMeta()
    pipeline = PipelineController(app_model, tracks_model, session_meta)

    # Real ingest: on folder drop, SessionMeta emits the session dir
    # and both list models refresh from core.file_matchers.
    session_meta.sessionOpened.connect(tracks_model.loadFromDir)
    session_meta.sessionOpened.connect(sources_model.loadFromDir)

    # Peaks extraction: once tracks populate, kick off a background
    # PeaksWorker. Strong refs (_peaks_*) keep the QThread alive until
    # the worker finishes; without them the GC would tear the thread
    # down mid-extract.
    _peaks_state: dict[str, object] = {"thread": None, "worker": None}

    def _on_audio_paths_changed(paths: list[tuple[int, str]]) -> None:
        # Tear down any prior worker — dropping a new folder supersedes
        # the previous peaks job.
        prev_thread = _peaks_state.get("thread")
        if isinstance(prev_thread, QThread):
            prev_worker = _peaks_state.get("worker")
            if isinstance(prev_worker, PeaksWorker):
                prev_worker.cancel()
            prev_thread.quit()
            prev_thread.wait()

        if not paths:
            _peaks_state["thread"] = None
            _peaks_state["worker"] = None
            return

        thread = QThread()
        worker = PeaksWorker(paths)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.peaksReady.connect(tracks_model.setPeaks)
        worker.allDone.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        _peaks_state["thread"] = thread
        _peaks_state["worker"] = worker
        thread.start()

    tracks_model.audioPathsChanged.connect(_on_audio_paths_changed)

    root_ctx = engine.rootContext()
    root_ctx.setContextProperty("appModel",       app_model)
    root_ctx.setContextProperty("preferences",    preferences)
    root_ctx.setContextProperty("modelRegistry",  model_registry)
    root_ctx.setContextProperty("tracksModel",    tracks_model)
    root_ctx.setContextProperty("sourcesModel",   sources_model)
    root_ctx.setContextProperty("sessionMeta",    session_meta)
    root_ctx.setContextProperty("pipeline",       pipeline)

    engine.load(QUrl.fromLocalFile(str(_QML_ROOT / "Main.qml")))
    if not engine.rootObjects():
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
