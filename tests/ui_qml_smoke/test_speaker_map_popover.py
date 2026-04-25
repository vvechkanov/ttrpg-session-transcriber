"""Smoke test: speaker_map editor populates rows + popover reachable.

Loads the e2e_p2 fixture session (which has a real ``speaker_map.json``
on disk), boots the full TimelineScreen QML tree via the same context
plumbing as :mod:`tests.test_qml_timeline_phases`, and asserts:

1. Each track row's ``CharactersRole`` / ``RoleRole`` reflect the
   on-disk speaker_map.
2. ``aggregatedCharacters`` returns the de-duped union of every PC
   row's characters.
3. The QML tree mounts cleanly without errors / warnings.

Run as part of the regular ``pytest tests/ui_qml_smoke/`` sweep when
``pytest-qt`` is installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Warm sources/__init__ before deep Qt imports.
from core.pipeline import run as _  # noqa: F401

from PySide6.QtCore import QObject, QUrl, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType
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


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QML_ROOT = _PROJECT_ROOT / "ui" / "qml"
_TIMELINE_QML = _QML_ROOT / "screens" / "TimelineScreen.qml"
_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "e2e_p2" / "session"


def _coerce_chars(characters) -> list[str]:
    """Turn the QML ``var characters`` payload into a plain ``list[str]``.

    QML signals declared with ``var`` types deliver QJSValue across the
    Python boundary; calling ``toVariant()`` flattens an array to a
    Python list. Already-Python values pass through.
    """

    from PySide6.QtQml import QJSValue
    if isinstance(characters, QJSValue):
        return list(characters.toVariant() or [])
    return list(characters or [])


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("speaker-map-popover-test")
    app.setOrganizationName("speaker-map-popover-test")
    return app


def _install_handler(collector: list[str]) -> None:
    def _handler(mode: QtMsgType, _ctx: QObject, message: str) -> None:
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            if "font directory" in message.lower():
                return
            collector.append(message)

    qInstallMessageHandler(_handler)


@pytest.mark.gui
def test_speaker_map_loads_into_model_and_qml_mounts() -> None:
    """End-to-end smoke: model populates from speaker_map + QML loads."""

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

    warnings: list[str] = []
    _install_handler(warnings)
    engine.load(QUrl.fromLocalFile(str(_TIMELINE_QML)))
    qInstallMessageHandler(None)

    roots = engine.rootObjects()
    assert roots, "TimelineScreen.qml failed to load"
    real_warnings = [w for w in warnings if "font" not in w.lower()]
    assert not real_warnings, "QML warnings on load:\n" + "\n".join(real_warnings)

    # Open the fixture session and let the model populate.
    runtime_warnings: list[str] = []
    _install_handler(runtime_warnings)
    session_meta.openSession(str(_FIXTURE))
    sources_model.loadFromDir(str(_FIXTURE))
    tracks_model.loadFromDir(str(_FIXTURE))
    app.processEvents()
    qInstallMessageHandler(None)

    assert not runtime_warnings, (
        "QML warnings during session load:\n" + "\n".join(runtime_warnings)
    )

    # Three tracks in the fixture: GM + two PC.
    assert tracks_model.rowCount() == 3

    # Pick out per-stem rows so we can assert independent of ordering.
    by_stem: dict[str, dict] = {}
    for row in range(tracks_model.rowCount()):
        idx = tracks_model.index(row, 0)
        stem = Path(tracks_model.audioPathFor(row)).stem
        by_stem[stem] = {
            "name": tracks_model.data(idx, TrackListModel.NameRole),
            "role": tracks_model.data(idx, TrackListModel.RoleRole),
            "characters": tracks_model.data(idx, TrackListModel.CharactersRole),
        }

    # GM track: no characters, role flips to "GM".
    assert by_stem["1-test_gm"]["role"] == "GM"
    assert by_stem["1-test_gm"]["characters"] == []
    assert by_stem["1-test_gm"]["name"] == "TestGM"

    # PC tracks pulled the legacy ``character`` field into a list.
    assert by_stem["2-test_player"]["role"] == "Игрок"
    assert by_stem["2-test_player"]["characters"] == ["Aragorn"]

    assert by_stem["3-test_player2"]["role"] == "Игрок"
    assert by_stem["3-test_player2"]["characters"] == ["Legolas"]

    # Cast strip aggregate: sorted, de-duped union of PC characters.
    assert tracks_model.aggregatedCharacters == ["Aragorn", "Legolas"]


@pytest.mark.gui
def test_save_speaker_map_round_trip(tmp_path: Path) -> None:
    """``saveSpeakerMapEntry`` mutates JSON and the model in-place."""

    app = _ensure_app()

    # Build a synthetic session next to the fixture so we don't mutate
    # the checked-in JSON file.
    session = tmp_path / "session"
    session.mkdir()
    (session / "1-alice.flac").write_bytes(b"fLaC-stub")

    app_model = AppModel()
    tracks_model = TrackListModel()
    session_meta = SessionMeta()
    session_meta.openSession(str(session))
    tracks_model.loadFromDir(str(session))

    pipeline = PipelineController(app_model, tracks_model, session_meta)

    pipeline.saveSpeakerMapEntry(0, "Alice", "PC", ["Aragorn", "Legolas"])
    app.processEvents()

    # JSON written.
    import json

    data = json.loads((session / "speaker_map.json").read_text(encoding="utf-8"))
    assert data["1-alice"]["player"] == "Alice"
    assert data["1-alice"]["characters"] == ["Aragorn", "Legolas"]
    assert data["1-alice"]["role"] == "PC"

    # Model row reflects the change.
    chars = tracks_model.data(tracks_model.index(0), TrackListModel.CharactersRole)
    assert chars == ["Aragorn", "Legolas"]
    assert tracks_model.aggregatedCharacters == ["Aragorn", "Legolas"]


@pytest.mark.gui
def test_popover_drives_save_signal_via_js_methods(tmp_path: Path) -> None:
    """Drive the popover through QML state (no faking saveSpeakerMapEntry).

    Mounts the real TimelineScreen.qml tree, opens a synthetic session,
    finds the SpeakerMapPopover via ``objectName``, and exercises its
    JS state machine: openFor, _addCharacter, _setCharacter,
    _removeCharacter, GM toggle, _commit. Asserts the ``saved`` signal
    fires with the manipulated payload — covers the JS paths the
    previous round-trip test bypassed by calling saveSpeakerMapEntry
    directly.
    """

    app = _ensure_app()
    QQuickStyle.setStyle("Basic")
    theme_url = QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml"))
    qmlRegisterSingletonType(theme_url, "App.Theme", 1, 0, "Theme")

    session = tmp_path / "session"
    session.mkdir()
    (session / "1-alice.flac").write_bytes(b"fLaC-stub")

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

    warnings: list[str] = []
    _install_handler(warnings)
    engine.load(QUrl.fromLocalFile(str(_TIMELINE_QML)))
    qInstallMessageHandler(None)

    roots = engine.rootObjects()
    assert roots, "TimelineScreen.qml failed to load"
    real_warnings = [w for w in warnings if "font" not in w.lower()]
    assert not real_warnings, "QML warnings on load:\n" + "\n".join(real_warnings)

    session_meta.openSession(str(session))
    sources_model.loadFromDir(str(session))
    tracks_model.loadFromDir(str(session))
    app.processEvents()

    # Locate the popover. SpeakerMapPopover.qml exposes
    # ``objectName: "speakerMapPopover"``; TimelineScreen instantiates
    # one with parent root, so it's a descendant of the screen root.
    popover = roots[0].findChild(QObject, "speakerMapPopover")
    assert popover is not None, "SpeakerMapPopover not found in QML tree"

    # Capture saved-signal payloads via a Python slot. The QML signal
    # declares ``var characters``, which crosses to Python as a
    # QJSValue rather than a Python list — call ``toVariant()`` so
    # downstream assertions can index it like a regular list.
    payloads: list[tuple] = []
    popover.saved.connect(
        lambda row, player, role, characters: payloads.append(
            (row, player, role, _coerce_chars(characters))
        )
    )

    # ── Drive the JS state ─────────────────────────────────────────
    # 1. Open the popover for row 0 (1-alice). No saved speaker_map
    #    yet, so initialPlayer is the empty string per the #3 fix.
    popover.openFor(0, "1-alice", "", "PC", [])
    app.processEvents()

    # 2. Add two characters via the JS method.
    popover.metaObject().invokeMethod(popover, "_addCharacter")
    popover.metaObject().invokeMethod(popover, "_addCharacter")
    # 3. Set their values via _setCharacter(idx, value).
    from PySide6.QtCore import Q_ARG
    popover.metaObject().invokeMethod(
        popover, "_setCharacter", Q_ARG("QVariant", 0), Q_ARG("QVariant", "Aragorn")
    )
    popover.metaObject().invokeMethod(
        popover, "_setCharacter", Q_ARG("QVariant", 1), Q_ARG("QVariant", "Legolas")
    )
    # 4. Add a third and immediately remove it — covers _removeCharacter.
    popover.metaObject().invokeMethod(popover, "_addCharacter")
    popover.metaObject().invokeMethod(
        popover, "_setCharacter", Q_ARG("QVariant", 2), Q_ARG("QVariant", "TempName")
    )
    popover.metaObject().invokeMethod(
        popover, "_removeCharacter", Q_ARG("QVariant", 2)
    )
    # 5. Toggle role → GM and back to PC. The GM hint section should
    #    surface; we confirm via the property write succeeding (state is
    #    JS-only, so we observe the resulting role on the saved payload).
    popover.setProperty("_role", "GM")
    popover.setProperty("_role", "PC")
    # 6. Set the player name through the working state property.
    popover.setProperty("_player", "Alice")

    # 7. Commit — fires `saved` and closes.
    popover.metaObject().invokeMethod(popover, "_commit")
    app.processEvents()

    assert len(payloads) == 1, f"expected exactly one saved emission, got {payloads}"
    row, player, role, characters = payloads[0]
    assert row == 0
    assert player == "Alice"
    assert role == "PC"
    assert characters == ["Aragorn", "Legolas"]


@pytest.mark.gui
def test_popover_gm_role_clears_characters_on_save(tmp_path: Path) -> None:
    """Toggling to GM and saving emits an empty characters list.

    The popover doesn't auto-clear ``_characters`` on the GM toggle —
    the characters section is hidden but the state list stays around
    so the user can flip back and resume editing without losing input.
    On save, however, an empty / GM-only flow should still produce a
    well-formed payload. This test pins the contract: with no
    characters added, GM commits an empty list.
    """

    app = _ensure_app()
    QQuickStyle.setStyle("Basic")
    theme_url = QUrl.fromLocalFile(str(_QML_ROOT / "Theme.qml"))
    qmlRegisterSingletonType(theme_url, "App.Theme", 1, 0, "Theme")

    session = tmp_path / "session"
    session.mkdir()
    (session / "1-gm.flac").write_bytes(b"fLaC-stub")

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

    engine.load(QUrl.fromLocalFile(str(_TIMELINE_QML)))
    roots = engine.rootObjects()
    assert roots
    session_meta.openSession(str(session))
    tracks_model.loadFromDir(str(session))
    app.processEvents()

    popover = roots[0].findChild(QObject, "speakerMapPopover")
    assert popover is not None

    payloads: list[tuple] = []
    popover.saved.connect(
        lambda row, player, role, characters: payloads.append(
            (row, player, role, _coerce_chars(characters))
        )
    )

    popover.openFor(0, "1-gm", "", "PC", [])
    app.processEvents()

    popover.setProperty("_role", "GM")
    popover.setProperty("_player", "MasterOfCeremonies")
    popover.metaObject().invokeMethod(popover, "_commit")
    app.processEvents()

    assert len(payloads) == 1
    _, player, role, characters = payloads[0]
    assert role == "GM"
    assert player == "MasterOfCeremonies"
    assert characters == []
