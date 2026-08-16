"""Smoke test: WaveformCanvas actually lays out bars for a real peak count.

``core.peaks`` emits ``DEFAULT_BIN_COUNT`` values per track and a lane is
on the order of a thousand pixels wide. The previous implementation put
one Repeater item per value with a fixed inter-bar gap, so the gaps alone
needed more room than the lane had and the computed bar width came out
negative — Qt draws nothing at a negative width, so no real session ever
rendered a waveform. Only the prototype's ~100 fake peaks fit.

These tests instantiate the component directly with a realistic peak
count and pin the invariant that broke: at least one bar, never more
bars than data, and geometry that fits inside the lane.
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
from PySide6.QtQuickControls2 import QQuickStyle

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QML_ROOT = _PROJECT_ROOT / "ui" / "qml"
_WAVEFORM_QML = _QML_ROOT / "timeline" / "WaveformCanvas.qml"

#: What core.peaks actually produces per track.
_REAL_PEAK_COUNT = 2000

#: Roughly the width of a track lane at a normal window size.
_LANE_WIDTH = 1180.0
_LANE_HEIGHT = 44.0


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("waveform-test")
    app.setOrganizationName("waveform-test")
    return app


@pytest.fixture(scope="module")
def engine():
    app = _ensure_app()
    QQuickStyle.setStyle("Basic")
    qmlRegisterSingletonType(
        QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml")), "App.Theme", 1, 0, "Theme"
    )
    eng = QQmlEngine()
    eng.addImportPath(str(_QML_ROOT))
    yield eng
    del app


#: Components created from QML default to JavaScript ownership, so the
#: engine is free to collect them the moment Python stops looking. Held
#: here for the module's lifetime instead.
_ALIVE: list = []


def _make(engine, peaks, width=_LANE_WIDTH, height=_LANE_HEIGHT):
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_WAVEFORM_QML)))
    assert component.status() == QQmlComponent.Ready, component.errorString()
    item = component.create()
    assert item is not None, component.errorString()
    QQmlEngine.setObjectOwnership(item, QQmlEngine.CppOwnership)
    _ALIVE.append((component, item))
    item.setProperty("width", width)
    item.setProperty("height", height)
    item.setProperty("peaks", peaks)
    return item


@pytest.mark.gui
def test_real_peak_count_produces_bars(engine):
    """The regression: 2000 peaks in a ~1180 px lane must still draw."""
    item = _make(engine, [0.5] * _REAL_PEAK_COUNT)
    bars = item.property("_barCount")
    assert bars > 0, (
        "no bars for a real peak count — the lane renders blank, which is "
        "exactly the bug this test exists for"
    )


@pytest.mark.gui
def test_bars_fit_the_lane(engine):
    """Bar pitch must leave every bar a positive width inside the lane."""
    item = _make(engine, [0.5] * _REAL_PEAK_COUNT)
    bars = item.property("_barCount")
    pad = item.property("_padX")
    gap = item.property("_gap")
    min_bar = item.property("_minBarWidth")

    pitch = (_LANE_WIDTH - 2 * pad) / bars
    assert pitch >= min_bar, f"pitch {pitch} leaves no room for a bar"
    assert pad + bars * pitch <= _LANE_WIDTH + 0.001, "bars overflow the lane"


@pytest.mark.gui
def test_never_more_bars_than_data(engine):
    """A short peak list must not be stretched into invented detail."""
    item = _make(engine, [0.5] * 12)
    assert item.property("_barCount") == 12


@pytest.mark.gui
@pytest.mark.parametrize("width", [0.0, 1.0, 4.0, 60.0, 320.0, 2400.0])
def test_no_bars_at_degenerate_widths(engine, width):
    """Collapsed and huge lanes must not produce nonsense counts."""
    item = _make(engine, [0.5] * _REAL_PEAK_COUNT, width=width)
    bars = item.property("_barCount")
    assert bars >= 0
    assert bars <= _REAL_PEAK_COUNT
    if width <= 2 * item.property("_padX"):
        assert bars == 0


@pytest.mark.gui
def test_empty_peaks_draw_nothing(engine):
    item = _make(engine, [])
    assert item.property("_barCount") == 0
