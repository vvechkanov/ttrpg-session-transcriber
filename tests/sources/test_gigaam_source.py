"""Unit tests for GigaAMSource Installable contract.

Tests isinstance check, name attribute, models_root override, and
is_installed logic (version.json present/missing, file tampering).
No sherpa_onnx, no network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("sherpa_onnx", MagicMock())


def _write_valid_version_json(module_dir: Path, files: dict[str, str]) -> None:
    """Write a minimal valid version.json with correct sizes for fake files."""
    from sources.speech._gigaam_paths import GIGAAM_SCHEMA_VERSION
    file_sizes = {relpath: (module_dir / relpath).stat().st_size
                  for relpath in files.values()
                  if (module_dir / relpath).is_file()}
    payload = {
        "schema_version": GIGAAM_SCHEMA_VERSION,
        "bundle_version": "v3-test",
        "variant": "rnnt",
        "precision": "fp32",
        "files": files,
        "file_sizes": file_sizes,
        "file_sha256": {relpath: "a" * 64 for relpath in files.values()},
    }
    (module_dir / "version.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class TestGigaamSourceInstallable:
    def test_isinstance_installable(self):
        from sources.base import Installable
        from sources.speech.gigaam import GigaAMSource
        assert isinstance(GigaAMSource(), Installable)

    def test_name_attribute(self):
        from sources.speech.gigaam import GigaAMSource
        assert GigaAMSource().name == "gigaam"

    def test_models_root_override_in_constructor(self, tmp_path):
        from sources.speech.gigaam import GigaAMSource
        src = GigaAMSource(models_root=tmp_path)
        assert src.models_root == tmp_path


class TestIsInstalled:
    def _make_params(self, tmp_path):
        from sources.speech.gigaam import GigaAMInstallParams, GigaAMPrecision, GigaAMVariant
        return GigaAMInstallParams(
            variant=GigaAMVariant.RNNT,
            precision=GigaAMPrecision.FP32,
            models_root=tmp_path,
        )

    def test_returns_false_when_no_version_json(self, tmp_path):
        from sources.speech.gigaam import GigaAMSource
        src = GigaAMSource(models_root=tmp_path)
        params = self._make_params(tmp_path)
        assert src.is_installed(params) is False

    def test_returns_true_when_version_json_and_all_files_exist(self, tmp_path):
        from sources.speech.gigaam import GigaAMSource, GigaAMInstallParams, GigaAMVariant, GigaAMPrecision
        from sources.speech._gigaam_paths import gigaam_module_dir

        params = self._make_params(tmp_path)
        module_dir = gigaam_module_dir(params)
        module_dir.mkdir(parents=True, exist_ok=True)

        # Create fake files
        fake_files = {
            "encoder": "encoder.onnx",
            "decoder": "decoder.onnx",
            "joiner": "joiner.onnx",
            "tokens": "tokens.txt",
            "vad": "silero_vad.onnx",
        }
        for relpath in fake_files.values():
            (module_dir / relpath).write_bytes(b"fake-content-placeholder")

        _write_valid_version_json(module_dir, fake_files)

        src = GigaAMSource(models_root=tmp_path)
        assert src.is_installed(params) is True

    def test_returns_false_when_file_missing_after_version_json(self, tmp_path):
        from sources.speech.gigaam import GigaAMSource
        from sources.speech._gigaam_paths import gigaam_module_dir

        params = self._make_params(tmp_path)
        module_dir = gigaam_module_dir(params)
        module_dir.mkdir(parents=True, exist_ok=True)

        fake_files = {
            "encoder": "encoder.onnx",
            "decoder": "decoder.onnx",
            "joiner": "joiner.onnx",
            "tokens": "tokens.txt",
            "vad": "silero_vad.onnx",
        }
        for relpath in fake_files.values():
            (module_dir / relpath).write_bytes(b"fake-content-placeholder")

        _write_valid_version_json(module_dir, fake_files)

        # Tamper: remove one file
        (module_dir / "encoder.onnx").unlink()

        src = GigaAMSource(models_root=tmp_path)
        assert src.is_installed(params) is False

    def test_returns_false_when_variant_mismatch_in_version_json(self, tmp_path):
        from sources.speech.gigaam import GigaAMSource
        from sources.speech._gigaam_paths import gigaam_module_dir, GIGAAM_SCHEMA_VERSION

        params = self._make_params(tmp_path)
        module_dir = gigaam_module_dir(params)
        module_dir.mkdir(parents=True, exist_ok=True)

        # Write version.json with wrong variant
        payload = {
            "schema_version": GIGAAM_SCHEMA_VERSION,
            "bundle_version": "v3-test",
            "variant": "e2e_rnnt",  # wrong!
            "precision": "fp32",
            "files": {},
            "file_sizes": {},
            "file_sha256": {},
        }
        (module_dir / "version.json").write_text(json.dumps(payload), encoding="utf-8")

        src = GigaAMSource(models_root=tmp_path)
        assert src.is_installed(params) is False
