"""QML snapshot tests for TimelineScreen in each of its 5 phases.

For each phase in ``("idle", "asr", "merge", "done", "failed")`` the test:

1. Loads ``TimelineScreen.qml`` with a full context (same as app_qml.main()).
2. Sets ``appModel.phase`` to the target phase.
3. Calls ``app.processEvents()`` so QML bindings re-evaluate.
4. Asserts no QML warnings or errors fired during the transition.
5. Verifies phase-specific visibility invariants:
   - ``done``   → DoneSummary visible,  FailedBanner hidden
   - ``failed`` → FailedBanner visible, DoneSummary hidden
   - ``idle``   → both banners hidden

DoneSummary and FailedBanner are found via ``objectName`` (``"doneSummary"``
and ``"failedBanner"``).  These names were added to the QML files as part
of this testing slice — the change is documented in FailedBanner.qml and
DoneSummary.qml.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import pytest

# Headless platform before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Warm sources/__init__ before deep Qt imports (same pattern as the other tests).
from core.pipeline import run as _  # noqa: F401

from PySide6.QtCore import QObject, QUrl, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
from PySide6.QtQuick import QQuickItem
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


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_QML_ROOT = _PROJECT_ROOT / "ui" / "qml"
_TIMELINE_QML = _QML_ROOT / "screens" / "TimelineScreen.qml"


# ---------------------------------------------------------------------------
# QGuiApplication singleton
# ---------------------------------------------------------------------------

def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("timeline-phase-test")
    app.setOrganizationName("timeline-phase-test")
    return app


# ---------------------------------------------------------------------------
# Engine + context factory
# (Re-use the same engine across parametrized invocations so the QML cache
#  stays warm.  Each test still sets a fresh phase on the same app_model.)
# ---------------------------------------------------------------------------

class _EngineContext:
    """Holds one QQmlApplicationEngine with all context properties set."""

    def __init__(self) -> None:
        self.app = _ensure_app()
        QQuickStyle.setStyle("Basic")

        # Theme singleton must be registered exactly once per process.
        # qmlRegisterSingletonType is idempotent — calling it again with the
        # same URI is a no-op (Qt prints a harmless debug note).
        theme_url = QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml"))
        qmlRegisterSingletonType(theme_url, "App.Theme", 1, 0, "Theme")

        self.app_model = AppModel()
        self.tracks_model = TrackListModel()
        self.sources_model = SourceListModel()
        self.session_meta = SessionMeta()
        self.pipeline = PipelineController(
            self.app_model, self.tracks_model, self.session_meta
        )
        self.preferences = AppPreferences()
        self.model_registry = ModelRegistry()

        self.engine = QQmlApplicationEngine()
        self.engine.addImportPath(str(_QML_ROOT))

        ctx = self.engine.rootContext()
        ctx.setContextProperty("appModel",      self.app_model)
        ctx.setContextProperty("preferences",   self.preferences)
        ctx.setContextProperty("modelRegistry", self.model_registry)
        ctx.setContextProperty("tracksModel",   self.tracks_model)
        ctx.setContextProperty("sourcesModel",  self.sources_model)
        ctx.setContextProperty("sessionMeta",   self.session_meta)
        ctx.setContextProperty("pipeline",      self.pipeline)

        # Collect warnings emitted during load.
        self._load_warnings: list[str] = []
        self._install_handler(self._load_warnings)
        self.engine.load(QUrl.fromLocalFile(str(_TIMELINE_QML)))
        qInstallMessageHandler(None)  # restore default after load

        roots = self.engine.rootObjects()
        assert roots, "TimelineScreen.qml failed to parse — rootObjects() is empty"
        self.root: QQuickItem = roots[0]

    @staticmethod
    def _install_handler(collector: list[str]) -> None:
        def _handler(mode: QtMsgType, _ctx: QObject, message: str) -> None:
            if mode in (
                QtMsgType.QtWarningMsg,
                QtMsgType.QtCriticalMsg,
                QtMsgType.QtFatalMsg,
            ):
                # Suppress the font-directory warning that fires in all
                # headless PySide6 runs — it is an environment issue, not
                # a QML correctness issue.
                if "font directory" in message.lower():
                    return
                collector.append(message)

        qInstallMessageHandler(_handler)

    def find_by_object_name(self, name: str) -> QQuickItem | None:
        """Return the first QQuickItem child whose objectName matches ``name``."""
        return self.root.findChild(QQuickItem, name)

    def set_phase(self, phase: str) -> list[str]:
        """Switch phase and process events; return any QML warnings collected."""
        warnings: list[str] = []
        self._install_handler(warnings)
        self.app_model.phase = phase
        self.app.processEvents()
        qInstallMessageHandler(None)
        return warnings


# Module-level singleton so the engine is created once.
_engine_ctx: _EngineContext | None = None


def _get_engine_ctx() -> _EngineContext:
    global _engine_ctx
    if _engine_ctx is None:
        _engine_ctx = _EngineContext()
    return _engine_ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.gui
def test_timeline_screen_loads_without_warnings():
    """TimelineScreen.qml parses clean — no QML warnings at load time."""
    ctx = _get_engine_ctx()
    assert ctx.root is not None, "root object is None"
    # Filter out font warnings (headless environment).
    real_warnings = [
        w for w in ctx._load_warnings if "font" not in w.lower()
    ]
    assert not real_warnings, (
        "QML warnings during TimelineScreen.qml load:\n" + "\n".join(real_warnings)
    )


@pytest.mark.gui
@pytest.mark.parametrize("phase", ["idle", "asr", "merge", "done", "failed"])
def test_timeline_phase_no_qml_errors(phase: str):
    """Switching to each phase must not produce QML errors or warnings."""
    ctx = _get_engine_ctx()
    warnings = ctx.set_phase(phase)
    # Any warning here is a genuine QML binding error — fail fast.
    assert not warnings, (
        f"QML warnings when switching to phase={phase!r}:\n" + "\n".join(warnings)
    )


@pytest.mark.gui
def test_timeline_idle_phase_both_banners_hidden():
    """In phase=idle both DoneSummary and FailedBanner must be hidden."""
    ctx = _get_engine_ctx()
    ctx.set_phase("idle")

    done_banner = ctx.find_by_object_name("doneSummary")
    failed_banner = ctx.find_by_object_name("failedBanner")

    assert done_banner is not None, (
        "DoneSummary not found by objectName='doneSummary' — "
        "ensure DoneSummary.qml has objectName: \"doneSummary\""
    )
    assert failed_banner is not None, (
        "FailedBanner not found by objectName='failedBanner' — "
        "ensure FailedBanner.qml has objectName: \"failedBanner\""
    )

    assert done_banner.property("visible") is False, (
        "DoneSummary must be hidden in idle phase"
    )
    assert failed_banner.property("visible") is False, (
        "FailedBanner must be hidden in idle phase"
    )


@pytest.mark.gui
def test_timeline_done_phase_shows_done_summary_hides_failed_banner():
    """In phase=done DoneSummary is visible and FailedBanner is hidden."""
    ctx = _get_engine_ctx()
    ctx.set_phase("done")

    done_banner = ctx.find_by_object_name("doneSummary")
    failed_banner = ctx.find_by_object_name("failedBanner")

    assert done_banner is not None, "DoneSummary not found"
    assert failed_banner is not None, "FailedBanner not found"

    assert done_banner.property("visible") is True, (
        "DoneSummary must be visible in done phase"
    )
    assert failed_banner.property("visible") is False, (
        "FailedBanner must be hidden in done phase"
    )


@pytest.mark.gui
def test_timeline_failed_phase_shows_failed_banner_hides_done_summary():
    """In phase=failed FailedBanner is visible and DoneSummary is hidden."""
    ctx = _get_engine_ctx()
    ctx.set_phase("failed")

    done_banner = ctx.find_by_object_name("doneSummary")
    failed_banner = ctx.find_by_object_name("failedBanner")

    assert done_banner is not None, "DoneSummary not found"
    assert failed_banner is not None, "FailedBanner not found"

    assert failed_banner.property("visible") is True, (
        "FailedBanner must be visible in failed phase"
    )
    assert done_banner.property("visible") is False, (
        "DoneSummary must be hidden in failed phase"
    )


@pytest.mark.gui
@pytest.mark.parametrize("phase", ["asr", "merge"])
def test_timeline_processing_phases_both_banners_hidden(phase: str):
    """In asr and merge phases both banners must be hidden."""
    ctx = _get_engine_ctx()
    ctx.set_phase(phase)

    done_banner = ctx.find_by_object_name("doneSummary")
    failed_banner = ctx.find_by_object_name("failedBanner")

    assert done_banner is not None, "DoneSummary not found"
    assert failed_banner is not None, "FailedBanner not found"

    assert done_banner.property("visible") is False, (
        f"DoneSummary must be hidden in phase={phase!r}"
    )
    assert failed_banner.property("visible") is False, (
        f"FailedBanner must be hidden in phase={phase!r}"
    )


@pytest.mark.gui
def test_timeline_root_phase_property_reflects_app_model():
    """The root QML item's ``phase`` property mirrors appModel.phase."""
    ctx = _get_engine_ctx()

    for phase in ("idle", "asr", "merge", "done", "failed"):
        ctx.set_phase(phase)
        root_phase = ctx.root.property("phase")
        assert root_phase == phase, (
            f"root.phase expected {phase!r}, got {root_phase!r}"
        )


@pytest.mark.gui
def test_timeline_failed_banner_shows_error_message():
    """In phase=failed the FailedBanner renders the errorMessage string."""
    ctx = _get_engine_ctx()
    error_text = "Test error: model crashed"
    ctx.app_model.setErrorMessage(error_text)
    ctx.set_phase("failed")

    failed_banner = ctx.find_by_object_name("failedBanner")
    assert failed_banner is not None, "FailedBanner not found"
    assert failed_banner.property("message") == error_text, (
        f"FailedBanner.message expected {error_text!r}, "
        f"got {failed_banner.property('message')!r}"
    )

    # Clean up for subsequent tests.
    ctx.app_model.setErrorMessage("")
    ctx.set_phase("idle")
