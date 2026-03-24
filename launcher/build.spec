# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for WhisperX-Transcriber bootstrap launcher.

Build with:
    cd launcher
    pyinstaller build.spec

The resulting EXE (~25-30MB) bundles:
  - bootstrap.py + installer_ui.py + install_logic.py + version.py
  - Python 3.12 embeddable package (as data in runtime/)
  - tkinter files for the embeddable package (as data in runtime/tkinter_files/)
  - scripts/*.py and prompts/*.md (as data)
"""

import os
import sys
import glob
import tkinter
from pathlib import Path

# Project root (parent of launcher/)
project_root = os.path.abspath(os.path.join(SPECPATH, '..'))

# --- Locate tkinter files to bundle for the embeddable Python ---

# Find tcl/tk directories
tcl_root = os.path.dirname(tkinter.__file__)
# tkinter's DLL and associated files
_tkinter_dll = None
for p in sys.path:
    candidate = os.path.join(p, '_tkinter.pyd')
    if os.path.exists(candidate):
        _tkinter_dll = candidate
        break

# tcl/tk library directories (e.g., C:\Python312\tcl\tcl8.6)
import _tkinter
tcl_lib = os.path.join(os.path.dirname(sys.executable), 'tcl')

tkinter_data = []

# _tkinter.pyd
if _tkinter_dll and os.path.exists(_tkinter_dll):
    tkinter_data.append((_tkinter_dll, os.path.join('runtime', 'tkinter_files')))

# tkinter Python package
tkinter_pkg = os.path.dirname(tkinter.__file__)
if os.path.isdir(tkinter_pkg):
    tkinter_data.append((tkinter_pkg, os.path.join('runtime', 'tkinter_files', 'tkinter')))

# tcl/tk libraries
if os.path.isdir(tcl_lib):
    for sub in os.listdir(tcl_lib):
        full = os.path.join(tcl_lib, sub)
        if os.path.isdir(full):
            tkinter_data.append((full, os.path.join('runtime', 'tkinter_files', sub)))

# tcl/tk DLLs (tcl86t.dll, tk86t.dll)
python_dir = os.path.dirname(sys.executable)
for pattern in ['tcl*.dll', 'tk*.dll', 'zlib*.dll']:
    for dll in glob.glob(os.path.join(python_dir, pattern)):
        tkinter_data.append((dll, os.path.join('runtime', 'tkinter_files')))
for dll_dir in ['DLLs']:
    dll_path = os.path.join(python_dir, dll_dir)
    if os.path.isdir(dll_path):
        for pattern in ['tcl*.dll', 'tk*.dll', '_tkinter*']:
            for dll in glob.glob(os.path.join(dll_path, pattern)):
                tkinter_data.append((dll, os.path.join('runtime', 'tkinter_files')))


# --- Collect data files ---

datas = [
    # Scripts
    (os.path.join(project_root, 'scripts', '*.py'), 'scripts'),
    # Prompts
    (os.path.join(project_root, 'prompts', '*.md'), 'prompts'),
    # Python embeddable package (must be placed manually before building)
    (os.path.join(SPECPATH, 'python-3.12.8-embed-amd64.zip'),
     os.path.join('runtime')),
]

# Add tkinter files
datas.extend(tkinter_data)


a = Analysis(
    ['bootstrap.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'installer_ui',
        'install_logic',
        'version',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages we don't need in the bootstrap
        'numpy', 'pandas', 'scipy', 'matplotlib', 'PIL',
        'torch', 'torchaudio', 'torchvision', 'whisperx',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
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
    console=False,           # No console window (windowed mode)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'icon.ico')
        if os.path.exists(os.path.join(project_root, 'icon.ico'))
        else None,
)
