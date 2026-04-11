# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ``WhisperX-Transcriber.exe`` (bootstrap launcher).

Post-migration (Epic A/B/C) this EXE is a small (~12-15 MB) launcher
whose only responsibilities are:

    1. Running the 3-stage installer UI (ffmpeg + ASR bundles via
       Epic A ``install_backend`` + session-transcriber runtime zip
       download from GitHub Releases).
    2. ``Popen``-ing ``%APPDATA%/ttrpg-transcriber/session-transcriber/``
       ``session-transcriber.exe`` on subsequent launches.

What we DO NOT bundle anymore (removed vs. legacy):
    * Python 3.12 embeddable zip (~15 MB) — we no longer extract a
      standalone Python into ``DATA_DIR``.
    * tkinter ``_tkinter.pyd`` / tcl-tk DLLs (~10 MB) as raw data —
      these were needed to feed the extracted embeddable; PyInstaller
      bundles the frozen installer's own tkinter automatically for
      the :mod:`launcher.installer_ui` window.
    * Source copies of ``ui/``, ``mergers/``, ``renderers/``,
      ``domain/``, ``scripts/``, ``prompts/`` — those lived in
      ``DATA_DIR`` for the old ``python -m ui`` launch path, which
      no longer exists. The runtime EXE carries its own code.

Build with::

    cd launcher
    pyinstaller build.spec
"""

import os

# ``SPECPATH`` is injected by PyInstaller into the spec file's namespace.
project_root = os.path.abspath(os.path.join(SPECPATH, '..'))  # noqa: F821

# ── Data files ──────────────────────────────────────────────────────────
#
# The installer only needs ``core.backend_installers`` + the
# ``sources.speech.*`` implementations to call ``install_backend``.
# PyInstaller's import analyser picks those up automatically via the
# Analysis step below, so no explicit ``datas`` are required — we keep
# an empty tuple for clarity.

datas: list[tuple[str, str]] = []

# Icon — optional, fall back to no icon if the file is missing.
_icon_candidates = [
    os.path.join(project_root, 'icon.ico'),
    os.path.join(project_root, 'assets', 'icon.ico'),
]
_icon_path = None
for _cand in _icon_candidates:
    if os.path.exists(_cand):
        _icon_path = _cand
        break


# ── Analysis ────────────────────────────────────────────────────────────
#
# ``pathex`` includes the project root so PyInstaller can resolve
# ``from core.backend_installers import ...`` and ``from sources.speech
# import ...``. ``hiddenimports`` lists the backend source modules
# explicitly because ``_resolve`` picks them by a runtime mapping —
# the static import tracer can miss branches.

a = Analysis(  # noqa: F821
    ['bootstrap.py'],
    pathex=[SPECPATH, project_root],  # noqa: F821
    binaries=[],
    datas=datas,
    hiddenimports=[
        'installer_ui',
        'install_logic',
        'version',
        # Epic A backend installer shim + source modules.
        'core.backend_installers',
        'sources.base',
        'sources.speech.faster_whisper',
        'sources.speech.gigaam',
        'sources.speech._bundle_download',
        'sources.speech._fw_download',
        'sources.speech._fw_models',
        'sources.speech._fw_paths',
        'sources.speech._fw_wheels',
        'sources.speech._gigaam_download',
        'sources.speech._gigaam_paths',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy ML stacks live inside the ASR bundles, not in the
        # installer EXE. Keep excluding them so PyInstaller does not
        # accidentally drag a system-wide copy.
        'numpy',
        'pandas',
        'scipy',
        'matplotlib',
        'PIL',
        'torch',
        'torchaudio',
        'torchvision',
        'faster_whisper',
        'whisperx',
        'sherpa_onnx',
        'gigaam',
        'librosa',
        'soundfile',
        'av',
        'transformers',
        'pyannote',
        # Runtime UI — lives in the separate session-transcriber.exe.
        'PySide6',
        'shiboken6',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WhisperX-Transcriber',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window — windowed bootstrap
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_path,
)
