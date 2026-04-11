"""Bootstrap entry point — compiled into ``WhisperX-Transcriber.exe``.

Post-migration flow (Epic A/B/C):

    1. Resolve ``DATA_DIR = %APPDATA%/ttrpg-transcriber``. This is the
       shared root that both the installer and the runtime use for
       ``models/<backend>/``, ``tools/ffmpeg/``, and
       ``session-transcriber/`` (the PySide6 shell).
    2. Check the ``.installed`` sentinel. If it exists **and** points
       at the current version **and** ``session-transcriber.exe`` is
       still on disk, jump straight to step 4.
    3. Otherwise, open :class:`launcher.installer_ui.InstallerWindow`.
       That worker runs three stages: ffmpeg, ASR models (via
       ``core.backend_installers.install_backend``), and runtime zip
       download from GitHub Releases.
    4. Spawn ``%APPDATA%/ttrpg-transcriber/session-transcriber/``
       ``session-transcriber.exe`` with the ``PATH`` extended by the
       local ffmpeg ``bin/`` directory, then exit. The bootstrap EXE
       is a launcher — it does not stay resident.

Legacy Python embeddable / pip-based install flow has been removed.
All ML stacks live inside the ASR backend bundles themselves
(see ``sources/speech/_fw_download.py`` and
``sources/speech/_bundle_download.py``).
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

# When running from a PyInstaller bundle, sys._MEIPASS points to the
# temporary directory where bundled data files are extracted. Kept for
# forward compatibility even though we no longer ship any bundled
# Python runtime / tkinter files.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

# Shared data root — same as ``default_models_root()`` in
# ``sources.speech._gigaam_paths`` and ``._fw_paths`` so the installer
# and the runtime see the same ``models/`` tree.
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "ttrpg-transcriber"

SENTINEL = DATA_DIR / ".installed"


def _get_version() -> str:
    """Get the current installer version string."""
    try:
        from launcher.version import VERSION
        return VERSION
    except ImportError:
        pass
    try:
        from version import VERSION  # type: ignore[no-redef]
        return VERSION
    except ImportError:
        return "0.0.0"


def _runtime_exe() -> Path:
    """Expected absolute path to the installed PySide6 runtime exe."""
    # Import lazily so the module is loadable even if install_logic is
    # missing during unit tests.
    try:
        from launcher.install_logic import RUNTIME_EXE_RELPATH
    except ImportError:
        from install_logic import RUNTIME_EXE_RELPATH  # type: ignore[no-redef]
    return DATA_DIR / RUNTIME_EXE_RELPATH


def _is_installed() -> bool:
    """Check that the sentinel matches our version AND the exe is on disk.

    Both checks matter: a stale sentinel from a failed upgrade or a
    user who deleted ``session-transcriber/`` manually should trigger
    a fresh install.
    """
    if not SENTINEL.exists():
        return False
    if not _runtime_exe().exists():
        return False
    try:
        data = json.loads(SENTINEL.read_text(encoding="utf-8"))
        return data.get("version") == _get_version()
    except Exception:
        return False


def _write_sentinel() -> None:
    """Write the ``.installed`` sentinel file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SENTINEL.write_text(
        json.dumps(
            {
                "version": _get_version(),
                "installed_at": datetime.datetime.now().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _launch_runtime() -> None:
    """Spawn ``session-transcriber.exe`` and detach.

    Extends the child process ``PATH`` with ``DATA_DIR/tools/ffmpeg/bin``
    so the runtime can find ``ffmpeg.exe`` without the user touching
    system PATH.
    """
    exe_path = _runtime_exe()
    if not exe_path.exists():
        _show_error(
            "Runtime приложение не найдено.\n"
            f"Ожидался файл: {exe_path}\n\n"
            "Попробуйте удалить каталог и запустить установщик заново:\n"
            f"  {DATA_DIR}"
        )
        return

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    ffmpeg_bin = DATA_DIR / "tools" / "ffmpeg" / "bin"
    if ffmpeg_bin.exists():
        existing_path = env.get("PATH", "")
        env["PATH"] = (
            str(ffmpeg_bin) + (os.pathsep + existing_path if existing_path else "")
        )

    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    subprocess.Popen(
        [str(exe_path)],
        cwd=str(exe_path.parent),
        env=env,
        startupinfo=startupinfo,
        creationflags=creationflags,
        close_fds=True,
    )


def _show_error(message: str) -> None:
    """Show an error dialog (tkinter — always available on Windows)."""
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
    """Show the installer UI and run a 3-stage install."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    def on_complete() -> None:
        """Called when installation finishes successfully."""
        _write_sentinel()
        _launch_runtime()

    try:
        from launcher.installer_ui import InstallerWindow
    except ImportError:
        from installer_ui import InstallerWindow  # type: ignore[no-redef]

    window = InstallerWindow(
        data_dir=DATA_DIR,
        version=_get_version(),
        on_complete=on_complete,
    )
    window.run()


def main() -> None:
    """Entry point."""
    if _is_installed():
        _launch_runtime()
    else:
        _run_installer()


if __name__ == "__main__":
    main()
