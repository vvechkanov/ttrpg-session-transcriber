"""Unit tests for :mod:`launcher.uninstall_logic`.

These tests cover the platform-independent pieces:

    * ``copy_self_to_data_dir`` — idempotency, skip-when-not-frozen.
    * ``uninstall_everything`` — wipes children, respects ``skip_self``,
      reports progress monotonically.
    * ``_dir_size_kb`` — sums files, ignores permission errors.

Registry tests are Windows-only and guarded by ``sys.platform``.
The ``winreg`` sub-key is written under an isolated test path so we
never touch the real Add/Remove Programs list of the dev machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from launcher import uninstall_logic


# ---------------------------------------------------------------------------
# copy_self_to_data_dir
# ---------------------------------------------------------------------------

def test_copy_self_returns_none_when_not_frozen(tmp_path: Path) -> None:
    # Running under pytest we are not a PyInstaller-frozen EXE, so the
    # function must short-circuit and return None.
    assert not getattr(sys, "frozen", False)
    assert uninstall_logic.copy_self_to_data_dir(tmp_path) is None


def test_copy_self_copies_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_exe = tmp_path / "src" / "WhisperX-Transcriber.exe"
    fake_exe.parent.mkdir()
    fake_exe.write_bytes(b"fake-exe-bytes")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    data_dir = tmp_path / "data"
    dst = uninstall_logic.copy_self_to_data_dir(data_dir)

    assert dst is not None
    assert dst == data_dir / "uninstall.exe"
    assert dst.read_bytes() == b"fake-exe-bytes"


def test_copy_self_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_exe = tmp_path / "src" / "WhisperX-Transcriber.exe"
    fake_exe.parent.mkdir()
    fake_exe.write_bytes(b"v1")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    data_dir = tmp_path / "data"
    dst1 = uninstall_logic.copy_self_to_data_dir(data_dir)
    assert dst1 is not None
    first_mtime = dst1.stat().st_mtime

    # Second call must not re-copy when the source mtime is unchanged.
    dst2 = uninstall_logic.copy_self_to_data_dir(data_dir)
    assert dst2 == dst1
    assert dst2.stat().st_mtime == first_mtime


# ---------------------------------------------------------------------------
# _dir_size_kb
# ---------------------------------------------------------------------------

def test_dir_size_kb_sums_files(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 2048)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"y" * 4096)

    size_kb = uninstall_logic._dir_size_kb(tmp_path)
    # 2048 + 4096 = 6144 bytes → 6 KB
    assert size_kb == 6


def test_dir_size_kb_missing_path_zero(tmp_path: Path) -> None:
    assert uninstall_logic._dir_size_kb(tmp_path / "nope") == 0


# ---------------------------------------------------------------------------
# uninstall_everything
# ---------------------------------------------------------------------------

def test_uninstall_everything_wipes_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "ttrpg-transcriber"
    data_dir.mkdir()
    (data_dir / "models").mkdir()
    (data_dir / "models" / "gigaam.bin").write_bytes(b"weights")
    (data_dir / "tools").mkdir()
    (data_dir / "tools" / "ffmpeg").mkdir()
    (data_dir / "tools" / "ffmpeg" / "ffmpeg.exe").write_bytes(b"ffmpeg")
    (data_dir / ".installed").write_text("{}", encoding="utf-8")

    # Stub registry removal — we don't want to touch HKCU.
    monkeypatch.setattr(
        uninstall_logic, "remove_uninstall_registry_entry", lambda: True
    )
    # Stub taskkill so the test is quiet on Windows too.
    monkeypatch.setattr(
        uninstall_logic, "_kill_running_runtime", lambda on_log: None
    )

    logs: list[str] = []
    progress: list[float] = []

    uninstall_logic.uninstall_everything(
        data_dir,
        on_log=logs.append,
        on_progress=progress.append,
    )

    # Everything gone or at least the children we created.
    assert not (data_dir / "models").exists()
    assert not (data_dir / "tools").exists()
    assert not (data_dir / ".installed").exists()

    # Progress is monotonic and reaches 1.0.
    assert progress[-1] == pytest.approx(1.0)
    assert all(progress[i] <= progress[i + 1] for i in range(len(progress) - 1))
    assert any("Удаление" in line for line in logs)


def test_uninstall_everything_respects_skip_self(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "ttrpg-transcriber"
    data_dir.mkdir()
    (data_dir / "models").mkdir()
    (data_dir / "models" / "weights.bin").write_bytes(b"x")
    keep = data_dir / "uninstall.exe"
    keep.write_bytes(b"stay")

    monkeypatch.setattr(
        uninstall_logic, "remove_uninstall_registry_entry", lambda: True
    )
    monkeypatch.setattr(
        uninstall_logic, "_kill_running_runtime", lambda on_log: None
    )

    uninstall_logic.uninstall_everything(
        data_dir,
        on_log=lambda *_: None,
        on_progress=lambda *_: None,
        skip_self=keep,
    )

    # Sibling deleted, kept file still there.
    assert not (data_dir / "models").exists()
    assert keep.exists()
    assert keep.read_bytes() == b"stay"


def test_uninstall_everything_missing_data_dir_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        uninstall_logic, "remove_uninstall_registry_entry", lambda: True
    )
    monkeypatch.setattr(
        uninstall_logic, "_kill_running_runtime", lambda on_log: None
    )

    progress: list[float] = []
    uninstall_logic.uninstall_everything(
        tmp_path / "does-not-exist",
        on_log=lambda *_: None,
        on_progress=progress.append,
    )
    assert progress == [1.0]


# ---------------------------------------------------------------------------
# Registry (Windows only)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="winreg is Windows-only")
def test_registry_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import winreg

    # Write to an isolated test key so we don't clobber the real one.
    test_key = (
        r"Software\WhisperX-Transcriber-Tests\TestUninstallRoundtrip"
    )
    monkeypatch.setattr(uninstall_logic, "_UNINSTALL_KEY", test_key)

    uninstall_exe = tmp_path / "uninstall.exe"
    uninstall_exe.write_bytes(b"fake")

    try:
        ok = uninstall_logic.write_uninstall_registry_entry(
            tmp_path, uninstall_exe, "9.9.9-test"
        )
        assert ok is True

        # Read back a couple of fields.
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, test_key)
        try:
            display_name, _ = winreg.QueryValueEx(key, "DisplayName")
            version, _ = winreg.QueryValueEx(key, "DisplayVersion")
            uninstall_cmd, _ = winreg.QueryValueEx(key, "UninstallString")
        finally:
            winreg.CloseKey(key)

        assert display_name == "WhisperX Transcriber"
        assert version == "9.9.9-test"
        assert "--uninstall" in uninstall_cmd
        assert str(uninstall_exe) in uninstall_cmd

        # Remove and confirm idempotency on a second delete.
        assert uninstall_logic.remove_uninstall_registry_entry() is True
        assert uninstall_logic.remove_uninstall_registry_entry() is True
    finally:
        # Best-effort cleanup of the test parent folder.
        try:
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\WhisperX-Transcriber-Tests",
            )
        except OSError:
            pass
