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
    """Write a minimal valid version.json in the new generic format.

    Epic A: version.json теперь пишется generic ``_bundle_download`` —
    список ``remote_files`` с relpath/size/sha256 вместо трёх
    параллельных словарей. Тесты пишут payload в том же формате
    напрямую, минуя реальный network-flow.
    """
    from sources.speech._gigaam_paths import GIGAAM_SCHEMA_VERSION

    remote_files = []
    for logical, relpath in files.items():
        p = module_dir / relpath
        size = p.stat().st_size if p.is_file() else 0
        remote_files.append(
            {
                "logical": logical,
                "relpath": relpath,
                "size": size,
                "sha256": "a" * 64,
                "url": f"https://example.test/{relpath}",
                "unpack": "none",
            }
        )
    payload = {
        "schema_version": GIGAAM_SCHEMA_VERSION,
        "bundle_version": "v3-test",
        "display_name": "GigaAM-v3",
        "variant": "rnnt",
        "precision": "fp32",
        "remote_files": remote_files,
        "local_files": [],
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
        from sources.speech._gigaam_paths import (
            GIGAAM_SCHEMA_VERSION,
            gigaam_module_dir,
        )

        params = self._make_params(tmp_path)
        module_dir = gigaam_module_dir(params)
        module_dir.mkdir(parents=True, exist_ok=True)

        # Write version.json with wrong variant (new generic format).
        payload = {
            "schema_version": GIGAAM_SCHEMA_VERSION,
            "bundle_version": "v3-test",
            "display_name": "GigaAM-v3",
            "variant": "e2e_rnnt",  # wrong!
            "precision": "fp32",
            "remote_files": [],
            "local_files": [],
        }
        (module_dir / "version.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        src = GigaAMSource(models_root=tmp_path)
        assert src.is_installed(params) is False
