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

Uninstall (L1 + L2)
-------------------
``WhisperX-Transcriber.exe --uninstall`` wipes ``DATA_DIR`` and
removes the Add/Remove Programs entry. On successful install a copy
of this EXE is placed at ``DATA_DIR/uninstall.exe`` and the HKCU
``Uninstall`` registry key points at it — so Windows' built-in
"Uninstall" button works even after the user deletes the original
download.

When the running EXE is the copy inside ``DATA_DIR`` we can't delete
it directly (Windows file lock on the process image), so we relocate
ourselves to ``%TEMP%`` and relaunch with ``--from-temp`` before
showing the UninstallerWindow.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
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

#: CLI flag used internally by ``_run_uninstaller`` to signal that the
#: currently-running EXE is already a temp copy and is free to delete
#: the original ``DATA_DIR/uninstall.exe``.
_FROM_TEMP_FLAG = "--from-temp"


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

    # Flags for launching a GUI child process from a windowed bootstrap.
    #
    # IMPORTANT: do NOT pass ``STARTUPINFO`` with ``STARTF_USESHOWWINDOW``.
    # That flag ships ``wShowWindow=SW_HIDE (0)`` into ``CreateProcess``,
    # which Windows applies to the child's *first* ``ShowWindow`` call —
    # so the PySide6 main window is created hidden and the user sees
    # nothing. ``STARTF_USESHOWWINDOW`` is the right choice for hiding
    # cli tools like ffmpeg, not for launching GUI apps.
    #
    # ``DETACHED_PROCESS`` gives the child its own process group so the
    # bootstrap can exit immediately without leaving the runtime tied
    # to our (already-gone) console. ``CREATE_NEW_PROCESS_GROUP`` is
    # added for the same reason — Ctrl-C in a dev console won't
    # propagate into the runtime.
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )

    subprocess.Popen(
        [str(exe_path)],
        cwd=str(exe_path.parent),
        env=env,
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


# ---------------------------------------------------------------------------
# L2 — Add/Remove Programs registration
# ---------------------------------------------------------------------------

def _refresh_uninstall_registration() -> None:
    """Copy the bootstrap EXE to ``DATA_DIR`` and refresh the registry.

    Idempotent and silent: called from both the post-install hook and
    every warm launch, so a user who deleted ``uninstall.exe`` or
    cleared the registry key manually gets it restored automatically.

    Failures are swallowed — Add/Remove Programs integration is a
    nice-to-have, not a blocker for the main launch path.
    """
    try:
        from launcher.uninstall_logic import (
            copy_self_to_data_dir,
            write_uninstall_registry_entry,
        )
    except ImportError:
        from uninstall_logic import (  # type: ignore[no-redef]
            copy_self_to_data_dir,
            write_uninstall_registry_entry,
        )

    try:
        dst = copy_self_to_data_dir(DATA_DIR)
        if dst is not None:
            write_uninstall_registry_entry(DATA_DIR, dst, _get_version())
    except Exception:
        # L2 is a best-effort integration point; do not break launch.
        pass


def _run_installer() -> None:
    """Show the installer UI and run a 3-stage install."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    def on_complete() -> None:
        """Called when installation finishes successfully."""
        _write_sentinel()
        _refresh_uninstall_registration()
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


# ---------------------------------------------------------------------------
# L1 — --uninstall flow
# ---------------------------------------------------------------------------

def _current_exe_path() -> Path | None:
    """Path of the running frozen EXE, or None when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def _running_from_data_dir() -> bool:
    """True if this EXE is the ``DATA_DIR/uninstall.exe`` copy.

    When True, deleting ``DATA_DIR`` will fail on Windows because the
    OS holds an exclusive lock on the running process image. The
    caller must relocate to ``%TEMP%`` before proceeding.
    """
    exe = _current_exe_path()
    if exe is None:
        return False
    try:
        return exe.parent.resolve() == DATA_DIR.resolve()
    except OSError:
        return False


def _relaunch_from_temp(original_exe: Path) -> None:
    """Copy this EXE to ``%TEMP%`` and relaunch with ``--from-temp``.

    After the copy is running, ``sys.exit(0)`` here releases the file
    lock on ``original_exe`` so the temp copy can delete it during
    the final cleanup pass.
    """
    tmp_root = Path(tempfile.mkdtemp(prefix="whisperx-uninstall-"))
    tmp_exe = tmp_root / "uninstall.exe"
    shutil.copy2(str(original_exe), str(tmp_exe))

    # The relaunched bootstrap is itself a GUI app (tkinter
    # UninstallerWindow). Same rules as ``_launch_runtime``: no
    # ``STARTF_USESHOWWINDOW``, otherwise the tkinter window opens
    # hidden and the user sees nothing happen after clicking Uninstall.
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )

    subprocess.Popen(
        [str(tmp_exe), "--uninstall", _FROM_TEMP_FLAG, str(original_exe)],
        cwd=str(tmp_root),
        creationflags=creationflags,
        close_fds=True,
    )


def _cleanup_after_uninstall(original_exe: Path | None) -> None:
    """Final pass: delete the original ``DATA_DIR/uninstall.exe``.

    Runs only when we were invoked with ``--from-temp``. After the
    delete succeeds DATA_DIR may now be empty, in which case we also
    try to remove it (best-effort).
    """
    if original_exe is None:
        return
    for _ in range(20):  # ~2 s — wait for parent process to release lock
        try:
            if original_exe.exists():
                original_exe.unlink()
            break
        except OSError:
            import time
            time.sleep(0.1)

    try:
        parent = original_exe.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


def _run_uninstaller(argv: list[str]) -> None:
    """Show the UninstallerWindow and wipe ``DATA_DIR``.

    If we are running from ``DATA_DIR/uninstall.exe`` and have not
    yet relocated to ``%TEMP%``, this function copies itself there
    and exits — the relaunched copy continues the flow. Otherwise
    it shows :class:`launcher.uninstaller_ui.UninstallerWindow` and
    schedules final self-deletion via :func:`_cleanup_after_uninstall`.
    """
    from_temp = _FROM_TEMP_FLAG in argv
    original_exe: Path | None = None
    if from_temp:
        # Argument layout: ``--uninstall --from-temp <original_exe>``
        try:
            idx = argv.index(_FROM_TEMP_FLAG)
            original_exe = Path(argv[idx + 1]).resolve()
        except (ValueError, IndexError):
            original_exe = None

    if not from_temp and _running_from_data_dir():
        exe = _current_exe_path()
        if exe is not None:
            try:
                _relaunch_from_temp(exe)
            except OSError as exc:
                _show_error(f"Не удалось подготовить деинсталлятор: {exc}")
                return
            sys.exit(0)

    # skip_self: if we're still the running exe inside DATA_DIR (shouldn't
    # happen after the relaunch above, but defensive) pass its path so
    # uninstall_everything skips it.
    skip_self: Path | None = None
    if not from_temp:
        exe = _current_exe_path()
        if exe is not None and _running_from_data_dir():
            skip_self = exe

    def on_complete() -> None:
        _cleanup_after_uninstall(original_exe)

    try:
        from launcher.uninstaller_ui import UninstallerWindow
    except ImportError:
        from uninstaller_ui import UninstallerWindow  # type: ignore[no-redef]

    window = UninstallerWindow(
        data_dir=DATA_DIR,
        skip_self=skip_self,
        on_complete=on_complete,
    )
    window.run()


def main() -> None:
    """Entry point."""
    argv = sys.argv[1:]
    if "--uninstall" in argv:
        _run_uninstaller(argv)
        return

    if _is_installed():
        _refresh_uninstall_registration()
        _launch_runtime()
    else:
        _run_installer()


if __name__ == "__main__":
    main()
