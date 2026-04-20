"""Tests for ``ui.models.session`` — Timeline screen view-models.

Focus of this file: iteration 3a of feature #3 — absolute-time
``startPct`` / ``endPct`` on ``SourceListModel`` rows. Covers:

* A session folder with real ``info.txt`` + ``Бой 1.txt`` produces
  non-zero, non-100 percentages for the combat row.
* A session folder without ``info.txt`` falls back to the legacy
  0..100% layout (no TimelineWindow can be built).
* ``SessionMeta.timelineWindow()`` is populated when the source
  list builds one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Warm the sources package before pulling Qt modules — matches the
# pattern from tests/test_ui_engines_pipeline_controller.py.
from core.pipeline import run as _  # noqa: F401

from PySide6.QtGui import QGuiApplication

from ui.models import SessionMeta, SourceListModel


def _ensure_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("session-model-test")
    app.setOrganizationName("session-model-test")
    return app


def _write_info(session: Path, start_iso: str) -> None:
    (session / "info.txt").write_text(
        f"Recording x\nStart time: {start_iso}\n",
        encoding="utf-8",
    )


def _write_combat(session: Path, name: str, started: str, ended: str) -> None:
    data = {
        "encounter_id": "x",
        "scene_name": "x",
        "started_at": started,
        "ended_at": ended,
        "initiative_order": [],
    }
    (session / name).write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )


def test_combat_row_percents_are_absolute_when_info_present(tmp_path: Path) -> None:
    """Combat whose times fall in the middle of the window renders mid-bar."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_info(session, "2026-04-09T17:21:29.274Z")
    _write_combat(
        session, "Бой 1.txt",
        "2026-04-09T19:25:33.183Z",
        "2026-04-09T20:45:45.523Z",
    )

    meta = SessionMeta()
    model = SourceListModel()
    model.setSessionMeta(meta)
    model.loadFromDir(str(session))

    # Exactly one row — the combat file.
    assert model.rowCount() == 1
    start_pct = model.data(model.index(0), SourceListModel.StartRole)
    end_pct = model.data(model.index(0), SourceListModel.EndRole)

    # Expected window: info_start .. info_start + 4h (default floor).
    # Combat starts at +2h4m4s = 124.07min / 240min = ~51.7%.
    # Combat ends at +3h24m16s = 204.27min / 240min = ~85.1%.
    assert 50.0 < start_pct < 53.0
    assert 84.0 < end_pct < 86.0

    # And SessionMeta got the window published back.
    window = meta.timelineWindow()
    assert window is not None
    assert window.t0.year == 2026


def test_no_info_no_sources_leaves_window_none(tmp_path: Path) -> None:
    """A folder without info.txt *and* without parseable combat/chat
    produces no window, so SessionMeta.timelineWindow stays ``None``."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()

    meta = SessionMeta()
    model = SourceListModel()
    model.setSessionMeta(meta)
    model.loadFromDir(str(session))

    assert model.rowCount() == 0
    assert meta.timelineWindow() is None


def test_no_info_with_combat_still_builds_window(tmp_path: Path) -> None:
    """When info.txt is missing, a valid combat span anchors the window
    on its own. The lone combat row renders at 0..100% because its
    bounds *are* the window bounds — but the window is still real."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_combat(
        session, "Бой 1.txt",
        "2026-04-09T19:25:33.183Z",
        "2026-04-09T20:45:45.523Z",
    )

    meta = SessionMeta()
    model = SourceListModel()
    model.setSessionMeta(meta)
    model.loadFromDir(str(session))

    assert model.rowCount() == 1
    start_pct = model.data(model.index(0), SourceListModel.StartRole)
    end_pct = model.data(model.index(0), SourceListModel.EndRole)
    # Combat *is* the window — its bounds collapse to 0..100.
    assert start_pct == pytest.approx(0.0)
    assert end_pct == pytest.approx(100.0)
    assert meta.timelineWindow() is not None


def test_malformed_combat_still_gets_a_row_fullwidth(tmp_path: Path) -> None:
    """A broken combat JSON still renders as a full-width row so the
    user isn't left wondering why their file disappeared."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_info(session, "2026-04-09T17:21:29.274Z")
    (session / "Бой 1.txt").write_text("{broken json", encoding="utf-8")

    meta = SessionMeta()
    model = SourceListModel()
    model.setSessionMeta(meta)
    model.loadFromDir(str(session))

    assert model.rowCount() == 1
    start_pct = model.data(model.index(0), SourceListModel.StartRole)
    end_pct = model.data(model.index(0), SourceListModel.EndRole)
    # Window exists (info.txt present) but combat parse failed →
    # full-width fallback for that single row.
    assert start_pct == 0.0
    assert end_pct == 100.0
