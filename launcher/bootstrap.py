"""
Bootstrap entry point — compiled into the single EXE via PyInstaller.

Logic:
  1. Determine DATA_DIR (%LOCALAPPDATA%/WhisperX-Transcriber)
  2. If .installed sentinel exists and version matches → launch app
  3. Otherwise → extract bundled assets, show installer UI, then launch app
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# When running from a PyInstaller bundle, sys._MEIPASS points to the
# temporary directory where bundled data files are extracted.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

# Persistent application data directory
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "WhisperX-Transcriber"

SENTINEL = DATA_DIR / ".installed"

_PROJECT_DIRS = ("ui", "core", "sources", "mergers", "renderers", "domain", "scripts", "prompts")


def _get_version() -> str:
    """Get the current version string."""
    try:
        from launcher.version import VERSION
        return VERSION
    except ImportError:
        pass
    try:
        from version import VERSION
        return VERSION
    except ImportError:
        return "0.0.0"


def _is_installed() -> bool:
    """Check if the app is already installed with the current version."""
    if not SENTINEL.exists():
        return False
    try:
        data = json.loads(SENTINEL.read_text(encoding="utf-8"))
        return data.get("version") == _get_version()
    except Exception:
        return False


def _write_sentinel() -> None:
    """Write the .installed sentinel file."""
    import datetime
    SENTINEL.write_text(
        json.dumps({
            "version": _get_version(),
            "installed_at": datetime.datetime.now().isoformat(),
        }, indent=2),
        encoding="utf-8",
    )


def _extract_project() -> None:
    """Extract all bundled runtime directories into DATA_DIR.

    P2: the six-layer package structure (ui, core, sources, mergers,
    renderers, domain) plus scripts (chunk_text.py post-processor) and
    prompts.
    """
    for folder in _PROJECT_DIRS:
        src = BUNDLE_DIR / folder
        dst = DATA_DIR / folder
        if src.exists() and src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)


def _find_python_zip() -> Path:
    """Find the bundled Python embeddable zip."""
    # Check in bundle (PyInstaller --add-data)
    bundled = BUNDLE_DIR / "runtime" / "python-3.12.8-embed-amd64.zip"
    if bundled.exists():
        return bundled

    # Check if already downloaded to DATA_DIR
    cached = DATA_DIR / "python-3.12.8-embed-amd64.zip"
    return cached  # install_logic will download if missing


def _find_tkinter_files() -> Path | None:
    """Find bundled tkinter files for the embeddable Python."""
    tk_dir = BUNDLE_DIR / "runtime" / "tkinter_files"
    if tk_dir.exists():
        return tk_dir
    return None


def _launch_app() -> None:
    """Launch the main GUI application via ``python -m ui``."""
    python_exe = DATA_DIR / "python" / "pythonw.exe"
    if not python_exe.exists():
        python_exe = DATA_DIR / "python" / "python.exe"

    if not python_exe.exists():
        _show_error(
            "Python runtime не найден.\n"
            f"Ожидался: {python_exe}\n\n"
            "Попробуйте удалить папку и запустить заново:\n"
            f"  {DATA_DIR}"
        )
        return

    ui_pkg = DATA_DIR / "ui" / "__main__.py"
    if not ui_pkg.exists():
        _show_error(
            "ui/__main__.py не найден.\n"
            f"Ожидался: {ui_pkg}\n\n"
            "Попробуйте удалить папку и запустить заново:\n"
            f"  {DATA_DIR}"
        )
        return

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # Make DATA_DIR importable so ``python -m ui`` resolves the six-layer
    # packages (ui, core, sources, mergers, renderers, domain).
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(DATA_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    )

    ffmpeg_bin = DATA_DIR / "tools" / "ffmpeg" / "bin"
    python_scripts = DATA_DIR / "python" / "Scripts"
    extra_path = []
    if python_scripts.exists():
        extra_path.append(str(python_scripts))
    if ffmpeg_bin.exists():
        extra_path.append(str(ffmpeg_bin))
    if extra_path:
        env["PATH"] = ";".join(extra_path + [env.get("PATH", "")])

    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    subprocess.Popen(
        [str(python_exe), "-m", "ui"],
        cwd=str(DATA_DIR),
        env=env,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )


def _show_error(message: str) -> None:
    """Show an error dialog."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("WhisperX Transcriber — Ошибка", message)
        root.destroy()
    except Exception:
        print(f"ERROR: {message}", file=sys.stderr)


def _run_installer() -> None:
    """Show the installer UI and run installation."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Extract project files first (installer doesn't need them, but
    # they'll be ready when the app launches)
    _extract_project()

    python_zip = _find_python_zip()
    tkinter_src = _find_tkinter_files()

    def on_complete() -> None:
        """Called when installation finishes successfully."""
        _write_sentinel()
        _launch_app()

    try:
        from launcher.installer_ui import InstallerWindow
    except ImportError:
        from installer_ui import InstallerWindow

    window = InstallerWindow(
        data_dir=DATA_DIR,
        python_zip=python_zip,
        tkinter_src=tkinter_src,
        scripts_dir=DATA_DIR / "scripts",
        on_complete=on_complete,
    )
    window.run()


def main() -> None:
    """Entry point."""
    if _is_installed():
        # Project files might have been updated in a new version
        _extract_project()
        _launch_app()
    else:
        _run_installer()


if __name__ == "__main__":
    main()
