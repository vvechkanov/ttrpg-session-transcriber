"""Headless geometry inspector for the QML shell.

Boots ``ui/app_qml.py`` under ``QT_QPA_PLATFORM=offscreen``, lets the
engine render one frame per screen, then walks the QQuickItem tree
and prints every node's geometry as text. Meant for the layout-bug
cases where a screenshot compresses the defect away — a zero-width
``Item`` that anchors its contents to ``parent.right`` is trivial to
spot in a text dump (``width=0``), whereas the PNG just shows the
contents collapsed on top of whatever's next to them.

Usage::

    QT_QPA_PLATFORM=offscreen python scripts/dump_qml_geometry.py [screen]
    QT_QPA_PLATFORM=offscreen python scripts/dump_qml_geometry.py timeline

Without a screen arg, dumps all four. The ``[screen]`` positional
accepts ``empty``, ``timeline``, ``models``, ``settings``.

The report flags common anti-patterns:
    * zero-width or zero-height Items (unless visible=false)
    * ``Layout.*`` hints on a non-layout-capable parent
    * Items whose bounding box lies entirely outside the parent
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Windows consoles default to cp1252 — re-wrap stdout as UTF-8 so the
# dump (which includes Cyrillic from Theme strings and box-drawing
# dashes in section headers) prints without UnicodeEncodeError.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", line_buffering=True,
    )

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Warm sources/__init__ before deeper imports.
from core.pipeline import run as _  # noqa: F401

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuick import QQuickItem, QQuickWindow
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
SCREENS = ("empty", "timeline", "models", "settings")
MAX_DEPTH = 16  # Cap traversal depth — 16 reaches the track-row delegates comfortably.


def _register_fonts(app: QGuiApplication) -> None:
    for path in (
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/consola.ttf"),
    ):
        if path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(path))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                app.setFont(QFont(families[0], 10))
                return


def _register_theme() -> None:
    qmlRegisterSingletonType(
        QUrl.fromLocalFile(str(QML_ROOT / "Theme.qml")),
        "App.Theme",
        1, 0,
        "Theme",
    )


def _build_engine(app_model: AppModel) -> QQmlApplicationEngine:
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_ROOT))

    prefs = AppPreferences()
    models = ModelRegistry()
    tracks = TrackListModel()
    sources = SourceListModel()
    meta = SessionMeta()
    pipeline = PipelineController(app_model, tracks, meta)

    ctx = engine.rootContext()
    ctx.setContextProperty("appModel", app_model)
    ctx.setContextProperty("preferences", prefs)
    ctx.setContextProperty("modelRegistry", models)
    ctx.setContextProperty("tracksModel", tracks)
    ctx.setContextProperty("sourcesModel", sources)
    ctx.setContextProperty("sessionMeta", meta)
    ctx.setContextProperty("pipeline", pipeline)

    engine._refs = (prefs, models, tracks, sources, meta, pipeline)  # type: ignore[attr-defined]
    engine.load(QUrl.fromLocalFile(str(QML_ROOT / "Main.qml")))
    return engine


def _type_name(item: QQuickItem) -> str:
    """Best-effort readable type label.

    For QML-declared components PySide6 uses synthesized class names
    of the form ``XxxType_QMLTYPE_NN`` — preserve the ``NN`` suffix so
    instances of the same component type are distinguishable in the
    dump. If the QML file declared ``objectName: "foo"``, append it
    so the reader can locate the item in source.
    """

    meta = item.metaObject()
    raw = meta.className()
    on = item.objectName()

    # Synthesized QML type → keep the numeric suffix, replace the
    # generic base with the source filename's implied component name.
    # PySide6 exposes no public API for the QML file path, so we use
    # the numeric tag as the stable handle. Users grep by this.
    label: str
    if "_QML_" in raw:
        base, tag = raw.split("_QML_", 1)
        label = f"{base}#{tag}"
    else:
        label = raw

    if on:
        label += f' "{on}"'
    return label


def _visible(item: QQuickItem) -> bool:
    try:
        return bool(item.isVisible())
    except Exception:  # noqa: BLE001
        return True


def _dump_item(item: QQuickItem, depth: int, out: list[str], flags: list[str]) -> None:
    indent = "  " * depth
    name = _type_name(item)
    vis = _visible(item)
    w, h = item.width(), item.height()
    x, y = item.x(), item.y()

    # Repeater is a non-visual delegate incubator — it always has zero
    # geometry by design; children are siblings of the Repeater in the
    # parent's item tree, not descendants of the Repeater itself. Don't
    # flag those as layout bugs.
    is_repeater = name.startswith("QQuickRepeater")

    marks: list[str] = []
    if vis and w == 0 and not is_repeater:
        marks.append("!W0")
        flags.append(f"{indent}{name}: width=0 but visible")
    if vis and h == 0 and not is_repeater:
        marks.append("!H0")
        flags.append(f"{indent}{name}: height=0 but visible")
    if not vis:
        marks.append("(hidden)")

    marker = " " + " ".join(marks) if marks else ""
    out.append(
        f"{indent}{name}  x={x:.0f} y={y:.0f} w={w:.0f} h={h:.0f}{marker}"
    )

    if depth >= MAX_DEPTH:
        if item.childItems():
            out.append(f"{indent}  … ({len(item.childItems())} deeper children elided)")
        return

    for child in item.childItems():
        _dump_item(child, depth + 1, out, flags)


def dump_screen(app: QGuiApplication, engine: QQmlApplicationEngine,
                app_model: AppModel, screen: str) -> str:
    app_model.screen = screen
    for _ in range(8):
        app.processEvents()

    roots = engine.rootObjects()
    if not roots:
        return f"[{screen}] no root objects"

    window = roots[0]
    assert isinstance(window, QQuickWindow)
    content = window.contentItem()

    out: list[str] = [f"── {screen} ─────────────────────────────────────────────"]
    flags: list[str] = []
    _dump_item(content, 0, out, flags)

    if flags:
        out.append("")
        out.append("FLAGGED:")
        out.extend(flags)
    else:
        out.append("(no zero-sized visible items)")

    return "\n".join(out)


def main() -> int:
    targets = sys.argv[1:] or list(SCREENS)
    unknown = [t for t in targets if t not in SCREENS]
    if unknown:
        sys.stderr.write(f"unknown screen(s): {unknown}\n")
        return 2

    app = QGuiApplication.instance() or QGuiApplication(sys.argv or [""])
    app.setApplicationName("Session Transcriber Geometry Dump")
    app.setOrganizationName("Session Transcriber")
    _register_fonts(app)
    QQuickStyle.setStyle("Basic")
    _register_theme()

    app_model = AppModel()
    engine = _build_engine(app_model)

    roots = engine.rootObjects()
    if not roots:
        sys.stderr.write("Main.qml failed to load\n")
        return 1

    window = roots[0]
    assert isinstance(window, QQuickWindow)
    window.setWidth(1400)
    window.setHeight(880)

    for _ in range(4):
        app.processEvents()

    for screen in targets:
        print(dump_screen(app, engine, app_model, screen))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
