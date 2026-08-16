"""Smoke test: the ASR progress fill sweeps the audio, not the lane.

The timeline window used to begin at the recording, so a track filled
the whole lane and a progress overlay drawn from x=0 was correct. Now
the window spans the whole session and the audio can start well into it
— a fill anchored at the left edge puts the ASR sweep across a stretch
that has no sound behind it.

Every case here runs at a progress the user can actually see. The
overlay is bound to ``_running``, which is ``progress > 0 && < 1``, so
asserting geometry at exactly 0.0 or 1.0 pins a rectangle that is never
drawn — an earlier version of this file did precisely that for five of
its eight cases.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterSingletonType
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QML_ROOT = _PROJECT_ROOT / "ui" / "qml"
_ROW_QML = _QML_ROOT / "timeline" / "TrackLaneRow.qml"

_ROW_WIDTH = 1400.0
_GUTTER = 220.0
_TRACK_WIDTH = _ROW_WIDTH - _GUTTER

#: Session 17's shape: the recording starts ~31% into the window.
_AUDIO_START_PCT = 30.8

#: Anything strictly between 0 and 1 — see the module docstring.
_VISIBLE = 0.6

_ALIVE: list = []


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("overlay-test")
    app.setOrganizationName("overlay-test")
    return app


@pytest.fixture(scope="module")
def engine():
    app = _ensure_app()  # held for the module's lifetime
    QQuickStyle.setStyle("Basic")
    qmlRegisterSingletonType(
        QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml")), "App.Theme", 1, 0, "Theme"
    )
    eng = QQmlEngine()
    eng.addImportPath(str(_QML_ROOT))
    yield eng
    del app


def _make_row(engine, *, segments, progress=_VISIBLE, excluded=False):
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_ROW_QML)))
    assert component.status() == QQmlComponent.Ready, component.errorString()
    item = component.create()
    assert item is not None, component.errorString()
    QQmlEngine.setObjectOwnership(item, QQmlEngine.CppOwnership)
    _ALIVE.append((component, item))

    item.setProperty("width", _ROW_WIDTH)
    item.setProperty("height", 54.0)
    item.setProperty("gutterWidth", _GUTTER)
    item.setProperty("segments", segments)
    item.setProperty("excluded", excluded)
    item.setProperty("progress", progress)
    return item


def _overlay(item) -> QQuickItem:
    found = item.findChild(QQuickItem, "progressOverlay")
    assert found is not None, "progressOverlay not found by objectName"
    return found


@pytest.mark.gui
def test_fill_starts_at_the_audio_not_the_lane_edge(engine):
    """The regression: an overlay at x=0 sits in silent time."""
    row = _make_row(
        engine,
        segments=[{"startPct": _AUDIO_START_PCT, "endPct": 100.0, "peaks": []}],
    )
    overlay = _overlay(row)
    assert overlay.property("visible") is True
    expected_x = _TRACK_WIDTH * (_AUDIO_START_PCT / 100.0)
    assert overlay.property("x") == pytest.approx(expected_x, abs=0.5)
    assert overlay.property("x") > 0.0


@pytest.mark.gui
@pytest.mark.parametrize("progress", [0.05, 0.25, 0.6, 0.99])
def test_fill_never_overshoots_the_audio(engine, progress):
    """At every visible progress the fill stays inside the sound.

    The load-bearing assertion is the upper bound: a width computed
    against the lane exceeds it at every progress, which is the bug.
    """
    row = _make_row(
        engine,
        segments=[{"startPct": _AUDIO_START_PCT, "endPct": 100.0, "peaks": []}],
        progress=progress,
    )
    overlay = _overlay(row)
    assert overlay.property("visible") is True
    width = overlay.property("width")
    assert 0 < width < _TRACK_WIDTH * progress
    right_edge = overlay.property("x") + width
    assert right_edge <= _TRACK_WIDTH + 0.5


@pytest.mark.gui
def test_fill_stops_short_of_a_lane_that_outlasts_the_audio(engine):
    """A recording shorter than the window must not paint the tail.

    build_window keeps a four-hour floor, so a three-hour session
    leaves silence on the right. Progress near the end has to stay
    left of it — this is the half of the fix that only works once
    segments carry a real duration.
    """
    row = _make_row(
        engine,
        segments=[{"startPct": _AUDIO_START_PCT, "endPct": 80.0, "peaks": []}],
        progress=0.99,
    )
    overlay = _overlay(row)
    right_edge = overlay.property("x") + overlay.property("width")
    assert right_edge < _TRACK_WIDTH * 0.80 + 0.5
    assert right_edge > _TRACK_WIDTH * 0.78


@pytest.mark.gui
def test_multiple_segments_sweep_from_first_to_last(engine):
    """A restarted recording leaves a gap; the sweep spans the union."""
    row = _make_row(
        engine,
        segments=[
            {"startPct": 20.0, "endPct": 40.0, "peaks": []},
            {"startPct": 60.0, "endPct": 90.0, "peaks": []},
        ],
        progress=0.99,
    )
    overlay = _overlay(row)
    assert overlay.property("x") == pytest.approx(_TRACK_WIDTH * 0.20, abs=0.5)
    right_edge = overlay.property("x") + overlay.property("width")
    assert right_edge < _TRACK_WIDTH * 0.90 + 0.5


@pytest.mark.gui
def test_no_segments_fills_the_whole_lane(engine):
    """The QML default, used by the prototype and by these tests."""
    row = _make_row(engine, segments=[], progress=0.99)
    overlay = _overlay(row)
    assert overlay.property("x") == pytest.approx(0.0, abs=0.5)
    assert overlay.property("width") == pytest.approx(
        _TRACK_WIDTH * 0.99, abs=1.0
    )


@pytest.mark.gui
@pytest.mark.parametrize("progress", [0.0, 1.0])
def test_overlay_is_hidden_outside_a_run(engine, progress):
    """Not started and finished are both "not running"."""
    row = _make_row(
        engine,
        segments=[{"startPct": _AUDIO_START_PCT, "endPct": 100.0, "peaks": []}],
        progress=progress,
    )
    assert _overlay(row).property("visible") is False


@pytest.mark.gui
def test_excluded_row_shows_no_progress(engine):
    row = _make_row(
        engine,
        segments=[{"startPct": _AUDIO_START_PCT, "endPct": 100.0, "peaks": []}],
        excluded=True,
    )
    assert _overlay(row).property("visible") is False


@pytest.mark.gui
def test_fill_follows_segments_when_they_change(engine):
    """Peaks land asynchronously, so the row is re-published mid-run.

    A stale extent would leave the sweep anchored where the audio used
    to be.
    """
    row = _make_row(
        engine, segments=[{"startPct": 10.0, "endPct": 50.0, "peaks": []}]
    )
    overlay = _overlay(row)
    assert overlay.property("x") == pytest.approx(_TRACK_WIDTH * 0.10, abs=0.5)

    row.setProperty("segments", [{"startPct": 40.0, "endPct": 90.0, "peaks": []}])
    assert overlay.property("x") == pytest.approx(_TRACK_WIDTH * 0.40, abs=0.5)


@pytest.mark.gui
@pytest.mark.parametrize(
    "segments",
    [
        [{"peaks": []}],
        [{"startPct": None, "endPct": None, "peaks": []}],
        [{"startPct": 80.0, "endPct": 20.0, "peaks": []}],
    ],
    ids=["missing-both", "null-both", "end-before-start"],
)
def test_malformed_segments_never_produce_negative_width(engine, segments):
    """Width must stay non-negative whatever the model hands over."""
    row = _make_row(engine, segments=segments)
    assert _overlay(row).property("width") >= 0.0
