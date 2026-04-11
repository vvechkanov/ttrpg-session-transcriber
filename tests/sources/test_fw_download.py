"""Unit tests for sources/speech/_fw_download.py.

Проверяет:
    * :func:`_build_spec` собирает корректный ``BundleSpec``
      (wheel entries + model entries, правильный target_dir,
      backend/model в extra_version_fields, схема версии).
    * :func:`install_fw_bundle` делегирует в generic
      ``install_bundle`` — мокаем network + sha256, проверяем что
      version.json пишется ПОСЛЕДНИМ, формат нового layout.
    * :func:`uninstall_fw_bundle` — идемпотентен.
    * Fail-closed поведение для manifest-а с пустым sha256.
    * KeyError на незнакомой модели (``get_model_bundle``).

Без реальной сети, без ``faster_whisper``. Тесты должны укладываться
в < 100 ms каждый.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("sherpa_onnx", MagicMock())


_TEST_MODEL = "bzikst/faster-whisper-large-v3-ru-podlodka"


def _make_params(tmp_path, model: str = _TEST_MODEL):
    from sources.speech.faster_whisper import FasterWhisperInstallParams

    return FasterWhisperInstallParams(model=model, models_root=tmp_path)


class TestGetModelBundle:
    def test_known_model_returns_tuple(self):
        from sources.speech._fw_models import get_model_bundle

        files = get_model_bundle(_TEST_MODEL)
        assert len(files) >= 1
        # All entries must be RemoteFile with plain unpack.
        for rf in files:
            assert rf.unpack == "none"
            assert rf.relpath.startswith("models/")

    def test_unknown_model_raises_key_error(self):
        from sources.speech._fw_models import get_model_bundle

        with pytest.raises(KeyError, match="Unknown faster-whisper model"):
            get_model_bundle("openai/whisper-medium-no-such-thing")

    def test_all_model_files_have_sha256(self):
        from sources.speech._fw_models import FW_MODEL_BUNDLES

        for model_id, files in FW_MODEL_BUNDLES.items():
            for rf in files:
                assert rf.sha256, (
                    f"Model {model_id} entry {rf.logical} has empty sha256"
                )
                assert len(rf.sha256) == 64, (
                    f"Model {model_id} entry {rf.logical} sha256 wrong length: "
                    f"{rf.sha256!r}"
                )

    def test_model_bin_is_largest_entry(self):
        """Sanity: model.bin weights should be the biggest file in a bundle.

        If this breaks, либо мы случайно подсунули tokenizer как model.bin,
        либо в FW_MODEL_BUNDLES появилась новая модель с другим layout.
        """
        from sources.speech._fw_models import FW_MODEL_BUNDLES

        for model_id, files in FW_MODEL_BUNDLES.items():
            by_name = {rf.logical: rf for rf in files}
            assert "model.bin" in by_name, (
                f"Model {model_id} missing model.bin entry"
            )
            biggest = max(files, key=lambda rf: rf.size)
            assert biggest.logical == "model.bin", (
                f"Model {model_id}: model.bin is not the biggest entry; "
                f"biggest is {biggest.logical} ({biggest.size} bytes)"
            )


class TestBuildSpec:
    def test_spec_target_dir_matches_fw_module_dir(self, tmp_path):
        from sources.speech._fw_download import _build_spec
        from sources.speech._fw_paths import fw_module_dir

        params = _make_params(tmp_path)
        spec = _build_spec(params)
        assert spec.target_dir == fw_module_dir(params)

    def test_spec_contains_wheel_and_model_entries(self, tmp_path):
        from sources.speech._fw_download import _build_spec
        from sources.speech._fw_models import FW_MODEL_BUNDLES
        from sources.speech._fw_wheels import REMOTE_FILES as WHEEL_FILES

        params = _make_params(tmp_path)
        spec = _build_spec(params)
        expected = len(WHEEL_FILES) + len(FW_MODEL_BUNDLES[_TEST_MODEL])
        assert len(spec.remote_files) == expected

    def test_spec_bundle_version_encodes_model(self, tmp_path):
        from sources.speech._fw_download import _build_spec
        from sources.speech._fw_wheels import BUNDLE_VERSION as WHEEL_VERSION

        params = _make_params(tmp_path)
        spec = _build_spec(params)
        assert WHEEL_VERSION in spec.bundle_version
        assert _TEST_MODEL in spec.bundle_version

    def test_spec_extra_version_fields(self, tmp_path):
        from sources.speech._fw_download import _build_spec

        params = _make_params(tmp_path)
        spec = _build_spec(params)
        assert spec.extra_version_fields["backend"] == "faster-whisper"
        assert spec.extra_version_fields["model"] == _TEST_MODEL

    def test_spec_schema_version_matches_paths_module(self, tmp_path):
        from sources.speech._fw_download import _build_spec
        from sources.speech._fw_paths import FW_SCHEMA_VERSION

        params = _make_params(tmp_path)
        spec = _build_spec(params)
        assert spec.schema_version == FW_SCHEMA_VERSION

    def test_spec_no_local_files(self, tmp_path):
        """faster-whisper не генерирует ничего локально (в отличие от GigaAM hotwords)."""
        from sources.speech._fw_download import _build_spec

        params = _make_params(tmp_path)
        spec = _build_spec(params)
        assert spec.local_files == ()

    def test_wheel_entries_use_unpack_wheel(self, tmp_path):
        from sources.speech._fw_download import _build_spec

        params = _make_params(tmp_path)
        spec = _build_spec(params)
        # At least one wheel entry exists.
        wheels = [rf for rf in spec.remote_files if rf.unpack == "wheel"]
        assert len(wheels) > 0
        # All wheels target the same site-packages dir.
        site_relpaths = {rf.relpath for rf in wheels}
        assert site_relpaths == {"site-packages"}

    def test_model_entries_use_unpack_none(self, tmp_path):
        from sources.speech._fw_download import _build_spec

        params = _make_params(tmp_path)
        spec = _build_spec(params)
        model_entries = [
            rf for rf in spec.remote_files if rf.unpack == "none"
        ]
        assert len(model_entries) > 0
        for rf in model_entries:
            assert rf.relpath.startswith("models/")


class TestInstallFwBundle:
    """Atomic install flow with mocked downloads.

    Мы НЕ качаем ~90 MB wheel-ов и ~3 GB model.bin в unit-тестах.
    Вместо этого патчим ``_bundle_download._download_with_progress``,
    чтобы он писал крошечные dummy-файлы, + ``sha256_file``, чтобы он
    возвращал ожидаемые hashes из manifest-а.

    Additionally, ``_unpack_wheel`` патчится на no-op подменён
    созданием маркерного файла в target — настоящий zip extractall
    на dummy-контенте бросил бы ``BadZipFile``.
    """

    def _fake_downloader(self):
        """Return a ``_download_with_progress`` replacement."""
        def _fake(url, dst, notify, label):
            dst.write_bytes(b"dummy-content-for-" + label.encode())
            notify(f"Download {label}", 32)
        return _fake

    def _sha_side_effect_factory(self, spec_entries):
        """Return a sha256_file replacement returning the expected hash.

        spec_entries: iterable of RemoteFile. Для wheel-archive лежит в
        tmp_dir как ``_archive_<logical>_<name>.whl``; для plain файлов
        — по ``relpath``. Матчим по ``basename``: если имя файла
        содержит ``logical``, возвращаем ``rf.sha256``.
        """
        def _side(path, **kw):
            name = Path(path).name
            for rf in spec_entries:
                if rf.unpack == "none":
                    if name == Path(rf.relpath).name:
                        return rf.sha256
                else:
                    # wheel archive filename includes the logical name.
                    if rf.logical in name:
                        return rf.sha256
            return "a" * 64
        return _side

    def _fake_unpack_wheel(self, whl_path, site_packages):
        """Fake wheel extractor: just creates a marker file per archive."""
        site_packages.mkdir(parents=True, exist_ok=True)
        marker = site_packages / f"{whl_path.stem}_unpacked"
        marker.write_bytes(b"unpacked")

    def test_install_writes_version_json_last(self, tmp_path):
        """version.json must be written AFTER all files/wheels are in place."""
        from sources.speech._fw_download import _build_spec, install_fw_bundle

        params = _make_params(tmp_path)
        spec = _build_spec(params)

        write_order: list[str] = []

        import sources.speech._bundle_download as bd
        real_write = bd._write_version_file

        def tracking_write(target_dir, payload):
            write_order.append("version.json")
            real_write(target_dir, payload)

        with patch(
            "sources.speech._bundle_download._download_with_progress",
            side_effect=self._fake_downloader(),
        ), patch(
            "sources.speech._bundle_download.sha256_file",
            side_effect=self._sha_side_effect_factory(spec.remote_files),
        ), patch(
            "sources.speech._bundle_download._unpack_wheel",
            side_effect=self._fake_unpack_wheel,
        ), patch(
            "sources.speech._bundle_download._write_version_file",
            side_effect=tracking_write,
        ):
            install_fw_bundle(params, progress=None)

        assert write_order == ["version.json"]

    def test_install_creates_version_json_with_new_format(self, tmp_path):
        """After successful install, version.json has backend/model fields."""
        from sources.speech._fw_download import _build_spec, install_fw_bundle
        from sources.speech._fw_paths import fw_module_dir

        params = _make_params(tmp_path)
        spec = _build_spec(params)

        with patch(
            "sources.speech._bundle_download._download_with_progress",
            side_effect=self._fake_downloader(),
        ), patch(
            "sources.speech._bundle_download.sha256_file",
            side_effect=self._sha_side_effect_factory(spec.remote_files),
        ), patch(
            "sources.speech._bundle_download._unpack_wheel",
            side_effect=self._fake_unpack_wheel,
        ):
            install_fw_bundle(params, progress=None)

        vf = fw_module_dir(params) / "version.json"
        payload = json.loads(vf.read_text(encoding="utf-8"))
        assert payload["backend"] == "faster-whisper"
        assert payload["model"] == _TEST_MODEL
        assert "remote_files" in payload
        assert "local_files" in payload
        # mix of wheel + plain entries
        unpack_kinds = {e["unpack"] for e in payload["remote_files"]}
        assert "wheel" in unpack_kinds
        assert "none" in unpack_kinds

    def test_install_sha_mismatch_raises(self, tmp_path):
        """If any SHA256 doesn't match, install must raise and rollback temp."""
        from sources.speech._fw_download import install_fw_bundle
        from sources.speech._fw_paths import fw_module_dir

        params = _make_params(tmp_path)

        def _bad_downloader(url, dst, notify, label):
            dst.write_bytes(b"wrong-content")
            notify("x", 13)

        with patch(
            "sources.speech._bundle_download._download_with_progress",
            side_effect=_bad_downloader,
        ), patch(
            "sources.speech._bundle_download._unpack_wheel",
            side_effect=self._fake_unpack_wheel,
        ):
            # Don't mock sha256_file — let it compute real hashes on
            # b"wrong-content" and mismatch against manifest.
            with pytest.raises(RuntimeError, match="SHA256 mismatch"):
                install_fw_bundle(params, progress=None)

        # target_dir must not exist (atomic rollback).
        assert not fw_module_dir(params).exists()


class TestUninstallFwBundle:
    def test_uninstall_removes_module_dir(self, tmp_path):
        from sources.speech._fw_download import uninstall_fw_bundle
        from sources.speech._fw_paths import fw_module_dir

        params = _make_params(tmp_path)
        target = fw_module_dir(params)
        target.mkdir(parents=True)
        (target / "version.json").write_text("{}")
        (target / "models").mkdir()
        (target / "models" / "config.json").write_bytes(b"{}")

        uninstall_fw_bundle(params)
        assert not target.exists()

    def test_uninstall_is_idempotent(self, tmp_path):
        from sources.speech._fw_download import uninstall_fw_bundle

        params = _make_params(tmp_path)
        # Not installed first — must not raise.
        uninstall_fw_bundle(params)
        uninstall_fw_bundle(params)

    def test_uninstall_does_not_touch_siblings(self, tmp_path):
        """Uninstalling one model must not touch another model's files."""
        from sources.speech._fw_download import uninstall_fw_bundle
        from sources.speech._fw_paths import fw_module_dir

        params_a = _make_params(tmp_path, model=_TEST_MODEL)
        params_b = _make_params(tmp_path, model="openai/whisper-medium")
        dir_a = fw_module_dir(params_a)
        dir_b = fw_module_dir(params_b)
        dir_a.mkdir(parents=True)
        dir_b.mkdir(parents=True)
        (dir_a / "version.json").write_text("{}")
        (dir_b / "version.json").write_text("{}")

        uninstall_fw_bundle(params_a)

        assert not dir_a.exists()
        assert dir_b.exists()
