"""The «Расширенные параметры распознавания» disclosure opens when clicked.

``TrackOverridePopover`` draws a chevron and a caption that look exactly
like the working disclosure in ``ui/qml/timeline/CastStrip.qml``. It was
not clickable at all: the ``MouseArea`` meant to be its hit zone was a
direct child of a ``ColumnLayout``, and a layout overrides the geometry
of its children. ``width: parent.width`` was recomputed to the item's
``implicitWidth`` — zero — and the ``y: -20`` that was supposed to lift
the zone onto the caption was replaced by the layout's own flow
position, putting it *below* the caption instead. Measured on the real
popover, offscreen, at the production width of 380::

    ROW    x=0.0   y=0.0   w=352.0  h=13.0
    LABEL  x=17.0  y=0.0   w=335.0  h=13.0
    MA     x=0.0   y=13.0  w=0.0    h=20.0

A zero-width zone cannot be hit anywhere, so the block behind the
disclosure never opened. What that block holds is a mock-up rather than
working settings — the VAD tags carry no handler at all, the punctuation
checkbox is bound to nothing, and language and beam size already work
globally from the Settings screen. So what these tests pin down is a
control that stopped being visibly broken, not settings that came within
reach; the block's own state is filed separately.

The tests press the caption in a real window rather than reading
geometry off the fixed item. That is deliberate and is what the mutation
check turned on: an assertion that "the hit zone is wider than zero"
passes on the broken code too, because after the fix the zone *is* the
header row, and the header row was 352px wide all along. Only delivering
a real ``QMouseEvent`` and watching ``_advanced`` flip distinguishes the
two.

``Main.qml`` rather than ``TimelineScreen.qml``: pointer events need a
window to be delivered into, and loading the screen on its own yields a
parentless ``Item`` with no window behind it.
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

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuick import QQuickItem, QQuickWindow
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
_MAIN_QML = _QML_ROOT / "Main.qml"

#: The caption of the disclosure under test, verbatim from the QML.
_CAPTION = "Расширенные параметры распознавания"

#: A caption from inside the advanced block. Used to prove the toggle
#: reaches what the user came for, not just a boolean.
_BODY_CAPTION = "VAD (ОБРЕЗАТЬ ТИШИНУ)"


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("track-override-advanced-test")
    app.setOrganizationName("track-override-advanced-test")
    return app


@dataclass
class _Harness:
    """Everything the mounted window needs kept alive.

    ``setContextProperty`` takes no ownership and gives the objects no
    QObject parent, so letting the locals go out of scope deletes the
    C++ side underneath a live QML tree — see the same note in
    :mod:`tests.ui_qml_smoke.test_session_tabs`.
    """

    app: QGuiApplication
    engine: QQmlApplicationEngine
    window: QQuickWindow
    context_objects: tuple[Any, ...]


def _mount() -> _Harness:
    """Show the real application window, wired as ``app_qml.py`` does."""

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

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(_QML_ROOT))
    ctx = engine.rootContext()
    ctx.setContextProperty("appModel", app_model)
    ctx.setContextProperty("preferences", preferences)
    ctx.setContextProperty("modelRegistry", model_registry)
    ctx.setContextProperty("tracksModel", tracks_model)
    ctx.setContextProperty("sourcesModel", sources_model)
    ctx.setContextProperty("sessionMeta", session_meta)
    ctx.setContextProperty("pipeline", pipeline)

    engine.load(QUrl.fromLocalFile(str(_MAIN_QML)))
    roots = engine.rootObjects()
    assert roots, "Main.qml failed to load"

    window = roots[0]
    assert isinstance(window, QQuickWindow), f"Main.qml root is {type(window)}"

    # The popover lives inside TimelineScreen, which is one page of the
    # shell's StackLayout. A page that is not current is not visible,
    # and an invisible ancestor swallows pointer events.
    app_model.screen = "timeline"

    window.resize(1280, 800)
    window.show()
    QTest.qWaitForWindowExposed(window)
    app.processEvents()

    return _Harness(
        app=app,
        engine=engine,
        window=window,
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


def _popover(harness: _Harness) -> QObject:
    """The TrackOverridePopover instance inside the mounted shell.

    Found by its own properties rather than by ``objectName``: reaching
    it through a name would make the test depend on a seam this fix
    added, and the seam is not what the card is about. ``_pendingId``
    plus ``currentModelId`` is unique to this popover —
    ``SpeakerMapPopover`` shares ``trackName`` and ``openFor`` but
    neither of those two.
    """

    matches = [
        child
        for child in harness.window.findChildren(QObject)
        if child.property("_pendingId") is not None
        and child.property("currentModelId") is not None
    ]
    assert len(matches) == 1, (
        f"expected exactly one TrackOverridePopover, found {len(matches)}"
    )
    return matches[0]


def _open(harness: _Harness) -> QObject:
    """Open the popover on a track and wait for it to lay out."""

    popover = _popover(harness)
    popover.openFor(0, "1-alice", "", False)
    harness.app.processEvents()

    assert popover.property("visible"), "popover did not become visible"
    assert popover.property("_advanced") is False, (
        "openFor is documented to reset the disclosure to closed"
    )
    return popover


def _descendants(item: QQuickItem) -> list[QQuickItem]:
    """Every item under ``item``, itself included, depth first.

    The visual tree, not ``findChildren``: items a ``Repeater`` creates
    belong to their QML context rather than to the QObject tree, so a
    recursive QObject search misses them even while they are on screen.
    """

    out = [item]
    for child in item.childItems():
        out.extend(_descendants(child))
    return out


def _text_item(popover: QObject, caption: str) -> QQuickItem:
    """The ``Text`` inside the popover whose content is ``caption``."""

    content = popover.property("contentItem")
    assert content is not None, "popover has no contentItem"

    found = [it for it in _descendants(content) if it.property("text") == caption]
    assert len(found) == 1, f"expected one item captioned {caption!r}, got {len(found)}"
    return found[0]


def _click(harness: _Harness, item: QQuickItem, at: QPointF) -> None:
    """Press and release at ``at``, given in ``item``'s coordinates."""

    QTest.mouseClick(
        harness.window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        item.mapToScene(at).toPoint(),
    )
    harness.app.processEvents()


def _centre(item: QQuickItem) -> QPointF:
    return QPointF(item.width() / 2, item.height() / 2)


@pytest.mark.gui
def test_clicking_the_caption_opens_the_disclosure() -> None:
    """The defect itself: pressing the caption did nothing at all."""

    harness = _mount()
    popover = _open(harness)
    label = _text_item(popover, _CAPTION)

    _click(harness, label, _centre(label))

    assert popover.property("_advanced") is True, (
        "clicking the caption did not open the advanced block"
    )


@pytest.mark.gui
def test_the_disclosure_closes_again() -> None:
    """A disclosure that only opens is half a control."""

    harness = _mount()
    popover = _open(harness)
    label = _text_item(popover, _CAPTION)

    _click(harness, label, _centre(label))
    assert popover.property("_advanced") is True

    _click(harness, label, _centre(label))
    assert popover.property("_advanced") is False, (
        "second click on the caption did not close the advanced block"
    )


@pytest.mark.gui
def test_hit_zone_spans_the_whole_caption() -> None:
    """Both ends of the caption respond, not just its middle.

    This is the card's «ширина хит-зоны больше нуля и она накрывает
    подпись», expressed as behaviour rather than as a number: the
    broken zone was 335px to the left of nothing, so a width assertion
    on the *row* would have passed while the row stayed unclickable.
    """

    harness = _mount()
    popover = _open(harness)
    label = _text_item(popover, _CAPTION)

    # Sanity guard, not the acceptance: this passes on the broken code
    # too. It only catches a harness where the layout never ran and the
    # two clicks below would land on top of each other at x=0.
    assert label.width() > 0, "the caption itself has no width — layout did not run"

    for name, x in (("left edge", 1.0), ("right edge", label.width() - 1.0)):
        popover.setProperty("_advanced", False)
        harness.app.processEvents()

        _click(harness, label, QPointF(x, label.height() / 2))

        assert popover.property("_advanced") is True, (
            f"the {name} of the caption is not clickable"
        )


@pytest.mark.gui
def test_hit_zone_is_taller_than_the_caption_glyphs() -> None:
    """A click just off the text still counts as a click on the row.

    The caption's own row is 13px. The broken zone asked for ``height:
    20`` and never got it; sizing the fix to the row alone would have
    left the thinnest click target in this file — the two working zones
    beside it are 24 and 46 tall. Pressing two pixels above and below
    the glyph band is how a user misses a 13px line, so that is what is
    checked here rather than the number itself.
    """

    harness = _mount()
    popover = _open(harness)
    label = _text_item(popover, _CAPTION)

    for name, y in (("above", -2.0), ("below", label.height() + 2.0)):
        popover.setProperty("_advanced", False)
        harness.app.processEvents()

        _click(harness, label, QPointF(label.width() / 2, y))

        assert popover.property("_advanced") is True, (
            f"a click two pixels {name} the caption missed the hit zone"
        )


@pytest.mark.gui
def test_clicking_the_chevron_opens_the_disclosure() -> None:
    """The chevron is drawn as part of the control, so it must act like it."""

    harness = _mount()
    popover = _open(harness)
    label = _text_item(popover, _CAPTION)

    # The chevron is the sibling that sits before the caption in the
    # header row; going through the row keeps the test independent of
    # how the icon itself is built.
    row = label.parentItem()
    chevron = [c for c in row.childItems() if c is not label]
    assert len(chevron) == 1, f"expected one sibling beside the caption, got {chevron}"

    _click(harness, chevron[0], _centre(chevron[0]))

    assert popover.property("_advanced") is True, (
        "clicking the chevron did not open the advanced block"
    )


@pytest.mark.gui
def test_opening_the_disclosure_reveals_the_advanced_block() -> None:
    """What the user came for — the parameters, not the boolean."""

    harness = _mount()
    popover = _open(harness)

    body_caption = _text_item(popover, _BODY_CAPTION)
    assert not body_caption.isVisible(), "the advanced block starts open"

    label = _text_item(popover, _CAPTION)
    _click(harness, label, _centre(label))

    assert body_caption.isVisible(), (
        "the advanced block stayed hidden after the disclosure opened"
    )


def _hover_cursor(harness: _Harness, item: QQuickItem, at: QPointF) -> Qt.CursorShape:
    """Cursor the window shows while the pointer sits at ``at``.

    The move is made from a known-neutral spot rather than from
    wherever the pointer happened to be: a cursor is only re-evaluated
    on an enter, so arriving from an unknown position can report the
    previous answer and pass for the right one.
    """

    QTest.mouseMove(harness.window, QPoint(1, 1))
    harness.app.processEvents()

    QTest.mouseMove(harness.window, item.mapToScene(at).toPoint())
    harness.app.processEvents()
    return harness.window.cursor().shape()


@pytest.mark.gui
def test_the_caption_shows_a_pointing_hand() -> None:
    """It looked clickable before it was; now the cursor tells the truth.

    Read against the popover's own padding, which is inert: asserting
    only that the caption shows a hand would also pass if the whole
    popover did.
    """

    harness = _mount()
    popover = _open(harness)
    label = _text_item(popover, _CAPTION)
    padding = popover.property("contentItem")

    assert _hover_cursor(harness, padding, QPointF(4, 4)) == Qt.CursorShape.ArrowCursor, (
        "the popover's inert padding already shows a hand — "
        "the cursor says nothing about the caption"
    )
    assert _hover_cursor(harness, label, _centre(label)) == (
        Qt.CursorShape.PointingHandCursor
    )
