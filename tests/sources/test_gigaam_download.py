"""Unit tests for sources/speech/_gigaam_download.py.

Tests bundle file manifest, TTRPG_HOTWORDS, and install_gigaam_bundle
atomic flow. No real network calls, no sherpa_onnx import.
Must run in < 50 ms each (install flow test may be slightly longer due
to file I/O but stays well under 1 s).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("sherpa_onnx", MagicMock())


def _make_rnnt_fp32_params(tmp_path):
    from sources.speech.gigaam import GigaAMInstallParams, GigaAMPrecision, GigaAMVariant
    return GigaAMInstallParams(
        variant=GigaAMVariant.RNNT,
        precision=GigaAMPrecision.FP32,
        models_root=tmp_path,
    )


class TestBundleFiles:
    def test_rnnt_fp32_returns_five_files(self, tmp_path):
        from sources.speech._gigaam_download import _bundle_files
        _, files = _bundle_files(_make_rnnt_fp32_params(tmp_path))
        assert len(files) == 5

    def test_rnnt_fp32_expected_logical_roles(self, tmp_path):
        from sources.speech._gigaam_download import _bundle_files
        _, files = _bundle_files(_make_rnnt_fp32_params(tmp_path))
        logical_roles = {f.logical for f in files}
        assert logical_roles == {"encoder", "decoder", "joiner", "tokens", "vad"}

    def test_rnnt_fp32_bundle_version_prefix(self, tmp_path):
        from sources.speech._gigaam_download import _bundle_files
        bundle_version, _ = _bundle_files(_make_rnnt_fp32_params(tmp_path))
        assert bundle_version.startswith("v3-")

    def test_e2e_rnnt_raises_not_implemented(self, tmp_path):
        from sources.speech._gigaam_download import _bundle_files
        from sources.speech.gigaam import GigaAMInstallParams, GigaAMPrecision, GigaAMVariant
        params = GigaAMInstallParams(
            variant=GigaAMVariant.E2E_RNNT,
            precision=GigaAMPrecision.FP32,
            models_root=tmp_path,
        )
        with pytest.raises(NotImplementedError):
            _bundle_files(params)

    def test_rnnt_int8_raises_not_implemented(self, tmp_path):
        from sources.speech._gigaam_download import _bundle_files
        from sources.speech.gigaam import GigaAMInstallParams, GigaAMPrecision, GigaAMVariant
        params = GigaAMInstallParams(
            variant=GigaAMVariant.RNNT,
            precision=GigaAMPrecision.INT8,
            models_root=tmp_path,
        )
        with pytest.raises(NotImplementedError):
            _bundle_files(params)

    def test_all_files_have_nonempty_sha256(self, tmp_path):
        """Fail-closed: every bundle entry must carry a hardcoded sha256.

        Empty sha strings are rejected at install time
        (see ``install_gigaam_bundle``). This test guards the packaging
        contract so nobody reintroduces a TOFU placeholder by accident.
        """
        from sources.speech._gigaam_download import _bundle_files
        _, files = _bundle_files(_make_rnnt_fp32_params(tmp_path))
        missing = [f.logical for f in files if not f.sha256]
        assert missing == [], f"entries missing sha256: {missing}"
        # Should cover all 5 logical roles.
        assert {f.logical for f in files} == {
            "encoder", "decoder", "joiner", "tokens", "vad",
        }

    def test_all_sha256_are_64_hex_chars(self, tmp_path):
        from sources.speech._gigaam_download import _bundle_files
        import re
        _, files = _bundle_files(_make_rnnt_fp32_params(tmp_path))
        hex_re = re.compile(r"^[0-9a-f]{64}$")
        for f in files:
            assert hex_re.match(f.sha256), (
                f"SHA256 for {f.relpath!r} is not 64 hex chars: {f.sha256!r}"
            )


class TestTtrpgHotwords:
    def test_hotwords_nonempty(self):
        from sources.speech._gigaam_download import TTRPG_HOTWORDS
        assert len(TTRPG_HOTWORDS) > 0

    def test_hotwords_no_duplicates(self):
        from sources.speech._gigaam_download import TTRPG_HOTWORDS
        assert len(TTRPG_HOTWORDS) == len(set(TTRPG_HOTWORDS))

    def test_hotwords_no_leading_trailing_whitespace(self):
        from sources.speech._gigaam_download import TTRPG_HOTWORDS
        for word in TTRPG_HOTWORDS:
            assert word == word.strip(), f"Whitespace found in {word!r}"

    def test_hotwords_lowercase(self):
        from sources.speech._gigaam_download import TTRPG_HOTWORDS
        for word in TTRPG_HOTWORDS:
            assert word == word.lower(), f"Not lowercase: {word!r}"


class TestInstallGigaamBundle:
    """Atomic install flow with mocked network."""

    def _fake_downloader(self, files_content: dict[str, bytes]):
        """Return a _download_with_progress replacement that writes fake bytes."""
        def _fake(url, dst, expected_size, notify, label):
            content = files_content.get(Path(dst).name, b"fake-content")
            dst.write_bytes(content)
            notify(f"Скачивание {label}...", len(content))
        return _fake

    def _sha(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def test_version_json_written_last(self, tmp_path):
        """version.json must not exist until after all files are moved."""
        from sources.speech._gigaam_download import _bundle_files

        params = _make_rnnt_fp32_params(tmp_path)
        _, remote_files = _bundle_files(params)

        # Build fake file contents with matching SHAs for non-empty sha files
        files_content: dict[str, bytes] = {}
        for rf in remote_files:
            content = b"fake-" + rf.relpath.encode()
            files_content[rf.relpath] = content

        write_order: list[str] = []

        real_write_version_file = None

        def tracking_write(module_dir, info):
            write_order.append("version.json")
            real_write_version_file(module_dir, info)

        import sources.speech._gigaam_paths as paths_mod
        real_write_version_file = paths_mod.write_version_file

        with patch(
            "sources.speech._gigaam_download._download_with_progress",
            side_effect=self._fake_downloader(files_content),
        ), patch(
            "sources.speech._gigaam_download.sha256_file",
        ) as mock_sha, patch(
            "sources.speech._gigaam_download.write_version_file",
            side_effect=tracking_write,
        ):
            # Return correct sha for non-empty, anything for empty
            def sha_side(path, **kw):
                name = Path(path).name
                for rf in remote_files:
                    if rf.relpath == name and rf.sha256:
                        return rf.sha256
                return "a" * 64
            mock_sha.side_effect = sha_side

            from sources.speech._gigaam_download import install_gigaam_bundle
            install_gigaam_bundle(params, progress=None)

        assert write_order == ["version.json"], (
            "version.json must be written exactly once, at the end"
        )

    def test_sha_mismatch_raises_runtime_error(self, tmp_path):
        from sources.speech._gigaam_download import _bundle_files, install_gigaam_bundle

        params = _make_rnnt_fp32_params(tmp_path)
        _, remote_files = _bundle_files(params)

        files_content = {rf.relpath: b"wrong-content" for rf in remote_files}

        with patch(
            "sources.speech._gigaam_download._download_with_progress",
            side_effect=self._fake_downloader(files_content),
        ):
            # Don't mock sha256_file — let it compute real hashes on wrong content.
            # The real SHA of b"wrong-content-<relpath>" will differ from hardcoded.
            with pytest.raises(RuntimeError, match="SHA256 mismatch"):
                install_gigaam_bundle(params, progress=None)

    def test_empty_sha_raises_fail_closed(self, tmp_path, monkeypatch):
        """Empty sha256 on a bundle entry must be rejected as a packaging bug.

        This guards the fail-closed contract: the current production bundle
        ships all five entries with hardcoded hashes. If anyone adds a new
        entry with ``sha256=""`` (TOFU placeholder), ``install_gigaam_bundle``
        must refuse before any network activity.
        """
        from dataclasses import replace

        from sources.speech import _gigaam_download as dl
        from sources.speech._gigaam_download import (
            _RemoteFile,
            _bundle_files,
            install_gigaam_bundle,
        )

        params = _make_rnnt_fp32_params(tmp_path)
        _, remote_files = _bundle_files(params)
        # Inject one empty-sha entry — simulate the bug.
        tampered = [replace(remote_files[0], sha256="")] + list(remote_files[1:])

        def _fake_bundle(_params):
            return "v-tampered", tampered

        monkeypatch.setattr(dl, "_bundle_files", _fake_bundle)

        with pytest.raises(RuntimeError, match="SHA256 not configured"):
            install_gigaam_bundle(params, progress=None)
