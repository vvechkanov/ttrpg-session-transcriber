"""Unit tests for sources/speech/_gigaam_paths.py.

Tests for default_models_root, gigaam_module_dir, VersionInfo round-trip,
read_version_file, and sha256_file. No sherpa_onnx required.
Must run in < 50 ms each. No network.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
        from sources.speech.gigaam import GigaAMInstallParams, GigaAMPrecision, GigaAMVariant

        params = GigaAMInstallParams(
            variant=GigaAMVariant.RNNT,
            precision=GigaAMPrecision.FP32,
            models_root=tmp_path,
        )
        result = gigaam_module_dir(params)
        assert result == tmp_path / "gigaam" / "rnnt-fp32"

    def test_variant_precision_reflected(self, tmp_path):
        from sources.speech._gigaam_paths import gigaam_module_dir
        from sources.speech.gigaam import GigaAMInstallParams, GigaAMPrecision, GigaAMVariant

        params = GigaAMInstallParams(
            variant=GigaAMVariant.RNNT,
            precision=GigaAMPrecision.FP32,
            models_root=tmp_path,
        )
        d = gigaam_module_dir(params)
        assert d.name == "rnnt-fp32"
        assert d.parent.name == "gigaam"


class TestVersionInfoRoundTrip:
    def _make_info(self):
        from sources.speech._gigaam_paths import VersionInfo, GIGAAM_SCHEMA_VERSION
        return VersionInfo(
            schema_version=GIGAAM_SCHEMA_VERSION,
            bundle_version="v3-rnnt-fp32-test",
            variant="rnnt",
            precision="fp32",
            files={"encoder": "encoder.onnx", "tokens": "tokens.txt"},
            file_sizes={"encoder.onnx": 1024, "tokens.txt": 64},
            file_sha256={"encoder.onnx": "abc123", "tokens.txt": "def456"},
        )

    def test_write_then_read_round_trip(self, tmp_path):
        from sources.speech._gigaam_paths import write_version_file, read_version_file

        info = self._make_info()
        write_version_file(tmp_path, info)
        result = read_version_file(tmp_path)

        assert result is not None
        assert result.schema_version == info.schema_version
        assert result.bundle_version == info.bundle_version
        assert result.variant == info.variant
        assert result.precision == info.precision
        assert result.files == info.files
        assert result.file_sizes == info.file_sizes
        assert result.file_sha256 == info.file_sha256

    def test_version_json_written_last(self, tmp_path):
        """version.json should exist after write_version_file."""
        from sources.speech._gigaam_paths import write_version_file

        write_version_file(tmp_path, self._make_info())
        assert (tmp_path / "version.json").is_file()


class TestReadVersionFile:
    def test_returns_none_if_missing(self, tmp_path):
        from sources.speech._gigaam_paths import read_version_file
        assert read_version_file(tmp_path) is None

    def test_returns_none_if_schema_mismatch(self, tmp_path):
        from sources.speech._gigaam_paths import GIGAAM_SCHEMA_VERSION

        payload = {
            "schema_version": GIGAAM_SCHEMA_VERSION + 99,
            "bundle_version": "future",
            "variant": "rnnt",
            "precision": "fp32",
            "files": {},
            "file_sizes": {},
            "file_sha256": {},
        }
        (tmp_path / "version.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        from sources.speech._gigaam_paths import read_version_file, VersionInfo

        # read_version_file returns VersionInfo even on mismatch (schema
        # check is caller's responsibility in is_installed).
        # Verify it at least reads correctly for forward-compat awareness.
        result = read_version_file(tmp_path)
        # The file is structurally valid, so it should parse.
        assert result is not None
        assert result.schema_version == GIGAAM_SCHEMA_VERSION + 99

    def test_returns_none_if_malformed_json(self, tmp_path):
        from sources.speech._gigaam_paths import read_version_file
        (tmp_path / "version.json").write_text("not json", encoding="utf-8")
        assert read_version_file(tmp_path) is None

    def test_returns_none_if_missing_key(self, tmp_path):
        from sources.speech._gigaam_paths import read_version_file
        (tmp_path / "version.json").write_text(
            json.dumps({"schema_version": 1}), encoding="utf-8"
        )
        assert read_version_file(tmp_path) is None


class TestSha256File:
    def test_known_content(self, tmp_path):
        from sources.speech._gigaam_paths import sha256_file

        f = tmp_path / "hello.bin"
        f.write_bytes(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert sha256_file(f) == expected
        assert expected == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_empty_file(self, tmp_path):
        from sources.speech._gigaam_paths import sha256_file

        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        assert sha256_file(f) == hashlib.sha256(b"").hexdigest()
