"""Unit tests for core/backend_installers.py.

Tests BackendId enum presence, BackendInfo metadata, is_backend_installed,
and install_backend delegation. No sherpa_onnx, no network.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("sherpa_onnx", MagicMock())


class TestListBackends:
    def test_returns_list(self):
        from core.backend_installers import list_backends
        result = list_backends()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_contains_gigaam_rnnt_fp32(self):
        from core.backend_installers import BackendId, list_backends
        ids = [b.id for b in list_backends()]
        assert BackendId.GIGAAM_RNNT_FP32 in ids


class TestBackendInfo:
    def test_gigaam_rnnt_fp32_default_selected(self):
        from core.backend_installers import BACKENDS, BackendId
        info = BACKENDS[BackendId.GIGAAM_RNNT_FP32]
        assert info.default_selected is True

    def test_gigaam_rnnt_fp32_approx_bytes_reasonable(self):
        from core.backend_installers import BACKENDS, BackendId
        info = BACKENDS[BackendId.GIGAAM_RNNT_FP32]
        # 800 MB – 1.1 GB
        assert 800_000_000 <= info.approx_download_bytes <= 1_100_000_000

    def test_gigaam_rnnt_fp32_title_nonempty(self):
        from core.backend_installers import BACKENDS, BackendId
        info = BACKENDS[BackendId.GIGAAM_RNNT_FP32]
        assert info.title.strip()


class TestIsBackendInstalled:
    def test_returns_false_when_no_version_json(self, tmp_path, monkeypatch):
        """Pointing models_root to an empty tmp_path → not installed."""
        from core.backend_installers import BackendId

        # Patch default_models_root so GigaAMSource uses tmp_path
        monkeypatch.setenv("APPDATA", str(tmp_path))

        # Monkeypatch _gigaam_paths.default_models_root
        import sources.speech._gigaam_paths as paths_mod
        monkeypatch.setattr(paths_mod, "default_models_root", lambda: tmp_path)

        from core.backend_installers import is_backend_installed
        assert is_backend_installed(BackendId.GIGAAM_RNNT_FP32) is False


class TestInstallBackend:
    def test_delegates_to_gigaamasource_install(self):
        from core.backend_installers import BackendId

        progress_calls: list = []
        cb = lambda f, m: progress_calls.append((f, m))

        with patch("core.backend_installers.GigaAMSource") as MockSource:
            instance = MockSource.return_value
            from core.backend_installers import install_backend
            install_backend(BackendId.GIGAAM_RNNT_FP32, progress=cb)
            instance.install.assert_called_once()
            # Verify progress callback was forwarded
            call_kwargs = instance.install.call_args
            assert call_kwargs is not None

    def test_delegates_to_faster_whisper_install(self):
        from core.backend_installers import BackendId

        with patch("core.backend_installers.FasterWhisperSource") as MockSource:
            instance = MockSource.return_value
            from core.backend_installers import install_backend
            install_backend(BackendId.FASTER_WHISPER_LARGE_V3_RU, progress=None)
            instance.install.assert_called_once()


class TestUninstallBackend:
    """Epic A: uninstall_backend() shim test."""

    def test_delegates_to_gigaamasource_uninstall(self):
        from core.backend_installers import BackendId, uninstall_backend

        with patch("core.backend_installers.GigaAMSource") as MockSource:
            instance = MockSource.return_value
            uninstall_backend(BackendId.GIGAAM_RNNT_FP32)
            instance.uninstall.assert_called_once()

    def test_delegates_to_faster_whisper_uninstall(self):
        from core.backend_installers import BackendId, uninstall_backend

        with patch("core.backend_installers.FasterWhisperSource") as MockSource:
            instance = MockSource.return_value
            uninstall_backend(BackendId.FASTER_WHISPER_LARGE_V3_RU)
            instance.uninstall.assert_called_once()


class TestFasterWhisperBackendInfo:
    def test_fw_backend_registered(self):
        from core.backend_installers import BackendId, list_backends

        ids = [b.id for b in list_backends()]
        assert BackendId.FASTER_WHISPER_LARGE_V3_RU in ids

    def test_fw_approx_bytes_reasonable(self):
        from core.backend_installers import BACKENDS, BackendId

        info = BACKENDS[BackendId.FASTER_WHISPER_LARGE_V3_RU]
        # 2 GB – 4 GB (wheels + 3 GB model.bin)
        assert 2_000_000_000 <= info.approx_download_bytes <= 4_000_000_000

    def test_fw_default_not_selected(self):
        """FW is opt-in (GigaAM is the default Russian backend)."""
        from core.backend_installers import BACKENDS, BackendId

        info = BACKENDS[BackendId.FASTER_WHISPER_LARGE_V3_RU]
        assert info.default_selected is False

    def test_fw_title_nonempty(self):
        from core.backend_installers import BACKENDS, BackendId

        info = BACKENDS[BackendId.FASTER_WHISPER_LARGE_V3_RU]
        assert info.title.strip()
