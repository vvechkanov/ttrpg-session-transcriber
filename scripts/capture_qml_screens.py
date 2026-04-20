"""Headless screenshot helper for the QML shell.

Boots ``ui/app_qml.py`` under ``QT_QPA_PLATFORM=offscreen``, switches
through each of the four screens in turn via ``appModel.screen``,
calls ``QQuickWindow.grabWindow()`` to render the current frame to a
``QImage``, and saves every frame as a PNG under
``docs/screenshots/qml/``.

Run:

    QT_QPA_PLATFORM=offscreen python scripts/capture_qml_screens.py

Replaces the deleted Widgets-era ``_capture_ui_screens.py`` that
grabbed QWidget trees. No handwritten rendering trickery — we just
ask Qt to render each screen once and dump the bitmap.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Warm sources/__init__ before any deeper imports (see tests).
from core.pipeline import run as _  # noqa: F401

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuick import QQuickWindow
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

QML_ROOT = ROOT / "ui" / "qml"
OUT_DIR = ROOT / "docs" / "screenshots" / "qml"

#: Screen identifiers in the order the sidebar lists them.
SCREENS = ("empty", "timeline", "models", "settings")


#: Windows system fonts to register before the engine loads. The
#: offscreen Qt platform can't discover system fonts on its own (Qt no
#: longer ships fonts and the offscreen backend doesn't bind to GDI),
#: so glyphs render as tofu ▢ rectangles. Loading Segoe UI directly
#: via QFontDatabase.addApplicationFont sidesteps the discovery
#: layer entirely.
_WIN_FONT_PATHS: tuple[Path, ...] = (
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/segoeuii.ttf"),
    Path("C:/Windows/Fonts/consola.ttf"),
)


def _register_fonts(app: QGuiApplication) -> None:
    registered_family: str | None = None
    for path in _WIN_FONT_PATHS:
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families and registered_family is None:
            registered_family = families[0]
    if registered_family is not None:
        # Force the default app font so QML bindings like
        # ``font.family: Theme.fontSans`` still resolve to something
        # renderable even when Theme's fontSans list doesn't cover the
        # loaded family.
        app.setFont(QFont(registered_family, 10))


def _register_theme() -> None:
    theme_url = QUrl.fromLocalFile(str(QML_ROOT / "Theme.qml"))
    qmlRegisterSingletonType(theme_url, "App.Theme", 1, 0, "Theme")


def _build_engine(app_model: AppModel) -> QQmlApplicationEngine:
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_ROOT))

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

    # Stash strong refs on the engine so the GC doesn't wipe them
    # mid-render — Python-owned QObjects set via setContextProperty
    # are only weakly held by the context.
    engine._refs = (
        preferences, model_registry, tracks_model,
        sources_model, session_meta, pipeline,
    )  # type: ignore[attr-defined]

    engine.load(QUrl.fromLocalFile(str(QML_ROOT / "Main.qml")))
    return engine


def capture_all() -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv or [""])
    app.setApplicationName("Session Transcriber Screenshot")
    app.setOrganizationName("Session Transcriber")
    QQuickStyle.setStyle("Basic")
    _register_fonts(app)
    _register_theme()

    app_model = AppModel()
    engine = _build_engine(app_model)

    roots = engine.rootObjects()
    if not roots:
        raise SystemExit("Main.qml failed to load")
    window = roots[0]
    if not isinstance(window, QQuickWindow):
        raise SystemExit(f"root object is not a QQuickWindow: {type(window).__name__}")

    window.setWidth(1400)
    window.setHeight(880)

    saved: list[Path] = []

    def _grab(name: str) -> None:
        # grabWindow() forces a render pass and returns a QImage. The
        # offscreen platform renders into a software backing store, so
        # the result is a real pixel-accurate frame.
        image = window.grabWindow()
        path = OUT_DIR / f"{name}.png"
        image.save(str(path))
        saved.append(path)

    # Process QML's initial layout pass before grabbing the first frame
    # — without this, the waveform Repeaters and Layout bindings haven't
    # settled and the empty-state card renders as a blank rectangle.
    app.processEvents()
    app.processEvents()

    for screen in SCREENS:
        app_model.screen = screen
        # Give QML a couple of event-loop ticks to rebind + re-layout.
        for _ in range(6):
            app.processEvents()
        _grab(screen)

    return saved


if __name__ == "__main__":
    paths = capture_all()
    for path in paths:
        size_kb = path.stat().st_size / 1024
        print(f"  {path.relative_to(ROOT)}  —  {size_kb:.1f} KB")
    print(f"OK: {len(paths)} screenshot(s) written under {OUT_DIR.relative_to(ROOT)}")
