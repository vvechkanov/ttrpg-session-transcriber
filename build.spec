# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Session Transcriber PySide6 GUI (ADR-017 Phase 10).

This spec packages the **application** — the PySide6 shell entry point at
``ui/shell/app.py`` — into a Windows folder-layout distribution (``dist/
session-transcriber/``) containing ``session-transcriber.exe`` plus the Qt
DLLs as *separate files* alongside the exe.

NOT onefile: see §Known risks / LGPL in docs/architecture/ui-qt-migration.md.
LGPL compliance for PySide6/Qt requires that the Qt dynamic libraries ship
as replaceable files, which ``--onefile`` violates by embedding them in a
self-extracting archive. This spec therefore sets ``onefile=False``.

Heavy ML stacks (PyTorch, faster-whisper, whisperx, GigaAM/sherpa) are
**excluded** from the bundle: they are installed on-demand by the existing
bootstrap launcher into ``%APPDATA%/ttrpg-transcriber`` on the user's
machine. The GUI exe only needs the pure-Python pipeline code + PySide6.

Build with:

    venv\\Scripts\\pyinstaller.exe build.spec --noconfirm --clean

The resulting directory ships as the GUI payload; the bootstrap EXE from
``launcher/build.spec`` stays separate and handles ML runtime provisioning.
"""

from __future__ import annotations

import os
from pathlib import Path

project_root = Path(SPECPATH).resolve()  # noqa: F821 — SPECPATH injected by PyInstaller

# ── Application metadata ────────────────────────────────────────────────

APP_NAME = "session-transcriber"
APP_ENTRY = str(project_root / "ui" / "shell" / "app.py")

# Icon — optional; fall back to no icon if the file is missing.
_icon_candidates = [
    project_root / "icon.ico",
    project_root / "assets" / "icon.ico",
    project_root / "docs" / "design" / "icon.ico",
]
_icon_path: str | None = None
for _cand in _icon_candidates:
    if _cand.exists():
        _icon_path = str(_cand)
        break


# ── Pure-Python source packages to bundle as data ───────────────────────

_RUNTIME_PACKAGES = (
    "core",
    "domain",
    "sources",
    "mergers",
    "renderers",
    "ui",
)

datas: list[tuple[str, str]] = []
for pkg in _RUNTIME_PACKAGES:
    pkg_root = project_root / pkg
    if not pkg_root.is_dir():
        continue
    for dirpath, _dirnames, filenames in os.walk(pkg_root):
        rel = os.path.relpath(dirpath, str(project_root))
        # Skip __pycache__ and legacy tkinter module
        if "__pycache__" in rel:
            continue
        for name in filenames:
            if not name.endswith(".py"):
                continue
            # Retire legacy tkinter entry point from the bundle; it lives
            # on in source as a transitional backup only (Phase 9).
            if name == "gui_legacy.py":
                continue
            datas.append((os.path.join(dirpath, name), rel))

# LGPL notice — mandatory beside the Qt DLLs so the user can find it.
_licenses_dir = project_root / "licenses"
if _licenses_dir.is_dir():
    for entry in _licenses_dir.iterdir():
        if entry.is_file():
            datas.append((str(entry), "licenses"))


# ── Qt module exclusions (reduce bundle size) ───────────────────────────
#
# The shell only uses QtCore, QtGui, QtWidgets. Everything else is dead
# weight on Windows and should be excluded so the bundle stays under the
# 120 MB ceiling the migration doc sets.

_QT_EXCLUDES = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtDBus",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
]

_HEAVY_ML_EXCLUDES = [
    # These stay in the on-demand runtime installed by the bootstrap
    # launcher into %APPDATA%/ttrpg-transcriber. Do NOT bundle them.
    "torch",
    "torchaudio",
    "torchvision",
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "sklearn",
    "transformers",
    "faster_whisper",
    "whisperx",
    "pyannote",
    "sherpa_onnx",
    "gigaam",
    "librosa",
    "soundfile",
    "av",
    "PIL",
    "tkinter",  # legacy UI, retired in Phase 9
]


# ── Analysis / PYZ / EXE / COLLECT ──────────────────────────────────────

a = Analysis(  # noqa: F821 — PyInstaller injects Analysis
    [APP_ENTRY],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Template modules are imported lazily via core.ui_registry —
        # PyInstaller can't see the importlib.import_module() call, so
        # we list them explicitly.
        "ui.templates.audio_source_template",
        "ui.templates.chat_source_template",
        "ui.templates.merger_template",
        "ui.templates.renderer_template",
        # Source backends are resolved through SPEECH_SOURCES.
        "sources.speech.gigaam",
        "sources.speech.faster_whisper",
        "sources.speech.whisperx",
        "sources.game_log.fvtt_chat",
        "mergers.script_merger",
        "renderers.plain_text",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_QT_EXCLUDES + _HEAVY_ML_EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # NOT onefile — required for LGPL compliance
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX can trip antivirus heuristics on Windows
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_path,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
