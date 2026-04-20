# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Session Transcriber PySide6 + QML GUI.

Phase 9 of the QML migration (``docs/architecture/ui-qml-migration.md``).
The spec packages the **application** — the thin QML loader at
``ui/app_qml.py`` — into a Windows folder-layout distribution
(``dist/session-transcriber/``) containing ``session-transcriber.exe``
plus the Qt DLLs as *separate files* alongside the exe.

NOT onefile: LGPL replaceability (see docs/adr/ADR-017) requires the
Qt dynamic libraries ship as replaceable files, which ``--onefile``
violates by embedding them in a self-extracting archive.

Heavy ML stacks (PyTorch, faster-whisper, whisperx, GigaAM/sherpa)
are **excluded** from the bundle: they are installed on-demand by
the bootstrap launcher into ``%APPDATA%/ttrpg-transcriber`` on the
user's machine. The GUI exe only needs the pure-Python pipeline code
+ PySide6 + QtQuick.

Build with:

    venv\\Scripts\\pyinstaller.exe build.spec --noconfirm --clean
"""

from __future__ import annotations

import os
from pathlib import Path

project_root = Path(SPECPATH).resolve()  # noqa: F821 — injected by PyInstaller

# ── Application metadata ────────────────────────────────────────────────

APP_NAME = "session-transcriber"
#: Thin QQmlApplicationEngine loader introduced in Phase 1. The Widgets
#: entry at ``ui/shell/app.py`` is retired in Phase 10.
APP_ENTRY = str(project_root / "ui" / "app_qml.py")

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
        if "__pycache__" in rel:
            continue
        for name in filenames:
            # Bundle .py AND QML-adjacent files under ui/qml. The QML
            # loader reads them from the filesystem at runtime; they
            # must land in the collect dir with the same relative
            # layout, so the (source, target_dir) tuple uses ``rel``
            # as-is.
            if name.endswith(".py") or (
                rel.replace("\\", "/").startswith("ui/qml")
                and name.endswith((".qml", ".js"))
            ):
                # Retire legacy tkinter entry point from the bundle.
                if name == "gui_legacy.py":
                    continue
                datas.append((os.path.join(dirpath, name), rel))

# Bundled ffmpeg/ffprobe for waveform peak extraction (Phase 5). They
# live under tools/ffmpeg/bin/ and are invoked by core.peaks via the
# absolute path derived from this repo layout.
_ffmpeg_bin = project_root / "tools" / "ffmpeg" / "bin"
if _ffmpeg_bin.is_dir():
    for entry in _ffmpeg_bin.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".exe":
            datas.append((str(entry), os.path.join("tools", "ffmpeg", "bin")))

# LGPL notice — mandatory beside the Qt DLLs so the user can find it.
_licenses_dir = project_root / "licenses"
if _licenses_dir.is_dir():
    for entry in _licenses_dir.iterdir():
        if entry.is_file():
            datas.append((str(entry), "licenses"))

# Handoff markdown — canonical design reference lives in the bundle
# too so the exe is self-documenting for contributors who receive
# only the dist folder.
_handoff_dir = project_root / "docs" / "handoff"
if _handoff_dir.is_dir():
    for entry in _handoff_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".md":
            datas.append((str(entry), os.path.join("docs", "handoff")))


# ── Qt module exclusions (reduce bundle size) ───────────────────────────
#
# The shell needs QtCore + QtGui + QtQml + QtQuick + QtQuickControls2 +
# QtQuickTemplates2 + QtSvg. Everything else is dead weight on Windows
# and is excluded so the bundle stays under the ~120 MB ceiling the
# migration doc set.

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
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtWidgets",   # Phase 10 snipes the Widgets shell — no QtWidgets needed after that
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
    "tkinter",  # legacy UI, retired in Phase 10
]


# ── Analysis / PYZ / EXE / COLLECT ──────────────────────────────────────

a = Analysis(  # noqa: F821 — PyInstaller injects Analysis
    [APP_ENTRY],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Source backends are resolved through SPEECH_SOURCES at
        # runtime; PyInstaller can't see dict lookups so we list them
        # explicitly.
        "sources.speech.gigaam",
        "sources.speech.faster_whisper",
        "sources.speech.whisperx",
        "sources.game_log.fvtt_chat",
        "mergers.script_merger",
        "renderers.plain_text",
        # Qt Quick Controls Basic style plugin — the QQuickStyle.setStyle
        # call in ui/app_qml.py is a string lookup, so PyInstaller can't
        # see it. Missing this on Windows manifests as "QtQuick.Controls:
        # No default style" at runtime.
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickTemplates2",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtSvg",
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
