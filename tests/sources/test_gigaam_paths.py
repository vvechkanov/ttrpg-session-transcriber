"""Unit tests for sources/speech/_gigaam_paths.py.

Tests for ``default_models_root``, ``gigaam_module_dir`` and the
re-exported ``sha256_file`` helper. No sherpa_onnx required.
Must run in < 50 ms each. No network.

Epic A note: ``VersionInfo`` / ``read_version_file`` / ``write_version_file``
были удалены из этого модуля — их роль взял на себя generic
``sources/speech/_bundle_download.py`` (общий формат version.json для
GigaAM + faster-whisper + whisperx). Соответствующие тесты живут в
``test_bundle_download.py``.
"""
from __future__ import annotations

import hashlib
import sys
from unittest.mock import MagicMock

# Stub out sherpa_onnx before any project import touches it.
sys.modules.setdefault("sherpa_onnx", MagicMock())


class TestDefaultModelsRoot:
    """Tests monkey-patch ``_current_os_name`` — NOT ``os.name`` directly.

    Mutating ``os.name`` on a running Windows system breaks ``pathlib.Path``
    globally and subsequently crashes pytest's own error-reporting.
    """

    def test_windows_uses_appdata(self, monkeypatch):
        import sources.speech._gigaam_paths as mod
        monkeypatch.setattr(mod, "_current_os_name", lambda: "nt")
        monkeypatch.setenv("APPDATA", r"C:\Users\TestUser\AppData\Roaming")

        root = mod.default_models_root()
        assert "ttrpg-transcriber" in str(root)
        assert "models" in str(root)
        # Path normalises separators on Windows → compare via parts.
        assert root.parts[0].lower().startswith("c:")

    def test_nonwindows_uses_xdg_data_home(self, monkeypatch, tmp_path):
        import sources.speech._gigaam_paths as mod
        monkeypatch.setattr(mod, "_current_os_name", lambda: "posix")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        monkeypatch.delenv("APPDATA", raising=False)

        root = mod.default_models_root()
        assert str(root).startswith(str(tmp_path / "xdg"))
        assert root.parts[-2] == "ttrpg-transcriber"
        assert root.parts[-1] == "models"

    def test_nonwindows_fallback_home(self, monkeypatch, tmp_path):
        import sources.speech._gigaam_paths as mod
        monkeypatch.setattr(mod, "_current_os_name", lambda: "posix")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.delenv("APPDATA", raising=False)

        root = mod.default_models_root()
        assert "ttrpg-transcriber" in str(root)
        assert root.parts[-1] == "models"


class TestGigaamModuleDir:
    def test_builds_correct_subpath(self, tmp_path):
        from sources.speech._gigaam_paths import gigaam_module_dir
        from sources.speech.gigaam import (
            GigaAMInstallParams,
            GigaAMPrecision,
            GigaAMVariant,
        )

        params = GigaAMInstallParams(
            variant=GigaAMVariant.RNNT,
            precision=GigaAMPrecision.FP32,
            models_root=tmp_path,
        )
        result = gigaam_module_dir(params)
        assert result == tmp_path / "gigaam" / "rnnt-fp32"

    def test_variant_precision_reflected(self, tmp_path):
        from sources.speech._gigaam_paths import gigaam_module_dir
        from sources.speech.gigaam import (
            GigaAMInstallParams,
            GigaAMPrecision,
            GigaAMVariant,
        )

        params = GigaAMInstallParams(
            variant=GigaAMVariant.RNNT,
            precision=GigaAMPrecision.FP32,
            models_root=tmp_path,
        )
        d = gigaam_module_dir(params)
        assert d.name == "rnnt-fp32"
        assert d.parent.name == "gigaam"


class TestSha256File:
    """``sha256_file`` is re-exported from ``_bundle_download``.

    Keeping a smoke test here guards the re-export contract so callers
    that import it from ``_gigaam_paths`` (backward-compat) continue
    to work.
    """

    def test_known_content(self, tmp_path):
        from sources.speech._gigaam_paths import sha256_file

        f = tmp_path / "hello.bin"
        f.write_bytes(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert sha256_file(f) == expected
        assert (
            expected
            == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )

    def test_empty_file(self, tmp_path):
        from sources.speech._gigaam_paths import sha256_file

        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        assert sha256_file(f) == hashlib.sha256(b"").hexdigest()
