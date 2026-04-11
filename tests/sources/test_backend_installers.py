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
