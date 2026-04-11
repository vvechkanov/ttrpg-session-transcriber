"""Uninstall logic for ``WhisperX-Transcriber.exe`` (L1 + L2).

Split into two layers:

    * **L1** — ``--uninstall`` mode of the bootstrap EXE. Wipes
      ``%APPDATA%/ttrpg-transcriber`` (models, ffmpeg, runtime zip,
      sentinel) and removes the Add/Remove Programs registry entry.
    * **L2** — Add/Remove Programs registration. On first successful
      install (and on every warm launch as a safety net) we copy the
      bootstrap EXE to ``DATA_DIR/uninstall.exe`` and register an
      ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall``
      entry whose ``UninstallString`` points at that stable copy. The
      copy is the trick that lets the user click "Uninstall" in
      Windows Settings even after they deleted the original download.

Everything is HKCU — no admin rights required, matching the per-user
installation model of the rest of the app.

All functions are Windows-specific and use the ``winreg`` stdlib
module. On non-Windows platforms the module still imports (for unit
testing) but every registry function is a no-op.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Registry sub-key under HKCU used by Add/Remove Programs. Windows
#: shows any immediate child of this key as an installed application.
_UNINSTALL_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperX-Transcriber"
)

#: DisplayName shown in Add/Remove Programs.
_APP_DISPLAY_NAME = "WhisperX Transcriber"

#: Publisher field in Add/Remove Programs. Purely cosmetic.
_APP_PUBLISHER = "vvechkanov"

#: Name of the stable copy of the bootstrap EXE inside ``DATA_DIR``.
#: This is what Windows' "Uninstall" button will launch — so it must
#: survive the user deleting the original Download folder.
_UNINSTALL_EXE_NAME = "uninstall.exe"

#: Flag passed to the relocated copy so it knows it can safely delete
#: the original without hitting a "file in use" lock on its own image.
_FROM_TEMP_FLAG = "--from-temp"

LogFn = Callable[[str], None]
ProgressFn = Callable[[float], None]


# ---------------------------------------------------------------------------
# Bootstrap EXE self-copy
# ---------------------------------------------------------------------------

def _current_exe_path() -> Path | None:
    """Absolute path of the running bootstrap EXE (PyInstaller-frozen).

    Returns ``None`` when running from source (e.g. ``python
    bootstrap.py``) — in that case there is no EXE to copy and the L2
    registration is silently skipped.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def copy_self_to_data_dir(data_dir: Path) -> Path | None:
    """Copy the running bootstrap EXE to ``data_dir/uninstall.exe``.

    Idempotent: if the destination already exists and is newer-or-equal
    than the source, nothing is copied. Returns the destination path on
    success, ``None`` when running from source.
    """
    src = _current_exe_path()
    if src is None:
        return None

    data_dir.mkdir(parents=True, exist_ok=True)
    dst = data_dir / _UNINSTALL_EXE_NAME

    try:
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
        shutil.copy2(str(src), str(dst))
    except OSError:
        # Copy may fail if the destination is the running EXE itself
        # (user launched bootstrap from DATA_DIR). That's fine — the
        # file is already where we want it.
        if dst.exists():
            return dst
        return None
    return dst


# ---------------------------------------------------------------------------
# Registry (Add/Remove Programs)
# ---------------------------------------------------------------------------

def _dir_size_kb(path: Path) -> int:
    """Approximate total size of ``path`` in KB (for EstimatedSize).

    Walks the tree once. Best-effort — permission errors are skipped
    silently because EstimatedSize is purely informational.
    """
    if not path.exists():
        return 0
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total // 1024


def write_uninstall_registry_entry(
    data_dir: Path,
    uninstall_exe: Path,
    version: str,
) -> bool:
    """Register the app in HKCU Add/Remove Programs.

    Returns True on success, False on any failure (non-Windows,
    permission denied, winreg import error). A failure here is not
    fatal — the app still works, the user just can't uninstall via
    Windows Settings.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False

    size_kb = _dir_size_kb(data_dir)
    uninstall_cmd = f'"{uninstall_exe}" --uninstall'

    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            _UNINSTALL_KEY,
            0,
            winreg.KEY_WRITE,
        )
    except OSError:
        return False

    try:
        winreg.SetValueEx(
            key, "DisplayName", 0, winreg.REG_SZ, _APP_DISPLAY_NAME
        )
        winreg.SetValueEx(
            key, "DisplayVersion", 0, winreg.REG_SZ, version
        )
        winreg.SetValueEx(
            key, "Publisher", 0, winreg.REG_SZ, _APP_PUBLISHER
        )
        winreg.SetValueEx(
            key, "InstallLocation", 0, winreg.REG_SZ, str(data_dir)
        )
        winreg.SetValueEx(
            key, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd
        )
        winreg.SetValueEx(
            key, "QuietUninstallString", 0, winreg.REG_SZ, uninstall_cmd
        )
        winreg.SetValueEx(
            key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb
        )
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except OSError:
        return False
    finally:
        winreg.CloseKey(key)
    return True


def remove_uninstall_registry_entry() -> bool:
    """Delete the Add/Remove Programs entry. Safe to call if absent."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY)
        return True
    except FileNotFoundError:
        return True  # already gone — treat as success
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Runtime shutdown
# ---------------------------------------------------------------------------

def _kill_running_runtime(on_log: LogFn) -> None:
    """Kill any running ``session-transcriber.exe`` before deletion.

    Uses ``taskkill`` which is always present on Windows. Failures are
    logged but not raised — ``shutil.rmtree`` below will surface a
    clearer error if files are still locked.
    """
    if sys.platform != "win32":
        return
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "session-transcriber.exe"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            on_log("Остановлено запущенное приложение session-transcriber.exe")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


# ---------------------------------------------------------------------------
# Top-level uninstall
# ---------------------------------------------------------------------------

def uninstall_everything(
    data_dir: Path,
    on_log: LogFn,
    on_progress: ProgressFn,
    skip_self: Path | None = None,
) -> None:
    """Wipe ``data_dir`` and remove the Add/Remove Programs entry.

    Order of operations:
        1. Kill running ``session-transcriber.exe`` (it lives inside
           ``data_dir`` and would lock its own files otherwise).
        2. Remove the registry entry FIRST — if step 3 fails partway
           we still want Add/Remove Programs to stop listing us.
        3. Walk top-level children of ``data_dir`` and delete them one
           by one, reporting progress. We skip ``skip_self`` (the
           relocated ``uninstall.exe`` copy living at the root — see
           :mod:`launcher.bootstrap` ``_run_uninstaller``).

    Args:
        data_dir: ``%APPDATA%/ttrpg-transcriber`` — the root.
        on_log: log sink callback.
        on_progress: 0.0-1.0 progress callback.
        skip_self: if given, a path that must NOT be deleted (typically
            the running ``uninstall.exe`` inside ``data_dir``). After a
            successful wipe the caller is responsible for scheduling
            its own deletion, usually via the ``--from-temp`` trick.
    """
    on_log("Остановка запущенных процессов...")
    _kill_running_runtime(on_log)

    on_log("Удаление записи в 'Программы и компоненты'...")
    if remove_uninstall_registry_entry():
        on_log("Запись реестра удалена.")
    else:
        on_log("Запись реестра не найдена или уже удалена.")

    if not data_dir.exists():
        on_log(f"Каталог данных отсутствует: {data_dir}")
        on_progress(1.0)
        return

    # Snapshot children first — we'll mutate the directory as we go.
    skip_resolved: Path | None = None
    if skip_self is not None:
        try:
            skip_resolved = skip_self.resolve()
        except OSError:
            skip_resolved = skip_self

    children = [
        c for c in data_dir.iterdir()
        if skip_resolved is None or c.resolve() != skip_resolved
    ]

    if not children:
        on_log("Нечего удалять.")
        on_progress(1.0)
        return

    total = len(children)
    for idx, child in enumerate(children):
        on_log(f"Удаление: {child.name}")
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=False)
            else:
                child.unlink(missing_ok=True)
        except OSError as exc:
            on_log(f"  ! не удалось удалить {child.name}: {exc}")
        on_progress((idx + 1) / total)

    # Try to delete DATA_DIR itself only if it's empty (skip_self may
    # still be living there). rmtree would nuke skip_self, so we use
    # rmdir() which fails silently on non-empty dirs.
    try:
        data_dir.rmdir()
        on_log(f"Удалён каталог: {data_dir}")
    except OSError:
        pass

    on_progress(1.0)
    on_log("Удаление данных завершено.")
