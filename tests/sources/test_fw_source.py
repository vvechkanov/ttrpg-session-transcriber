"""Unit tests for FasterWhisperSource Installable contract.

Проверяет:
    * isinstance(FasterWhisperSource(), Installable)
    * ``FasterWhisperInstallParams`` дефолты и override ``models_root``
    * ``is_installed`` — все граничные случаи (нет version.json,
      schema mismatch, wrong backend label, wrong model, missing files,
      всё OK)
    * ``installed_size_bytes`` — 0 для пустого каталога, положителен
      после записи файлов
    * ``uninstall`` — идемпотентен и удаляет target dir
    * ``_prepend_site_packages`` — raises на отсутствующем каталоге,
      idempotent на повторных вызовах, правильный порядок в sys.path

Реальный ``install()`` (который тянет ~90 MB wheel-ов и 3 GB модель)
в unit-тестах не вызывается. Для него отдельный integration smoke
test под marker-ом будет добавлен в test_fw_download.py на следующей
итерации.

No network, no faster_whisper, no sherpa_onnx — быстрые in-memory
тесты под < 50 ms каждый.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# sherpa_onnx всё ещё нужен, т.к. sources/__init__.py грузит GigaAMSource,
# который lazy-импортит sherpa_onnx только в ``extract()``, но conftest /
# другие тесты могли уже поставить stub — делаем безопасно.
sys.modules.setdefault("sherpa_onnx", MagicMock())


_TEST_MODEL = "bzikst/faster-whisper-large-v3-ru-podlodka"


def _write_valid_version_json(
    module_dir: Path,
    *,
    model: str = _TEST_MODEL,
    schema_version: int | None = None,
    backend: str = "faster-whisper",
    remote_entries: list[dict] | None = None,
) -> None:
    """Write a minimal valid version.json in the generic format.

    Для faster-whisper есть два типа записей в remote_files:
        * обычные HF-файлы модели (``unpack="none"``) — проверяются по
          точному размеру;
        * wheel-ы (``unpack="wheel"``) — проверяется только, что
          каталог распаковки существует и непуст.
    """
    from sources.speech._fw_paths import FW_SCHEMA_VERSION

    if schema_version is None:
        schema_version = FW_SCHEMA_VERSION

    if remote_entries is None:
        # Default: один wheel-каталог + один plain-файл модели.
        remote_entries = [
            {
                "logical": "faster-whisper",
                "relpath": "site-packages",
                "size": 12345,
                "sha256": "a" * 64,
                "url": "https://files.pythonhosted.org/fake.whl",
                "unpack": "wheel",
            },
            {
                "logical": "config.json",
                "relpath": "models/config.json",
                "size": (module_dir / "models/config.json").stat().st_size
                if (module_dir / "models/config.json").is_file()
                else 0,
                "sha256": "b" * 64,
                "url": f"https://huggingface.co/{model}/resolve/main/config.json",
                "unpack": "none",
            },
        ]

    payload = {
        "schema_version": schema_version,
        "bundle_version": "fw-1.0.3+test",
        "display_name": f"faster-whisper / {model}",
        "backend": backend,
        "model": model,
        "remote_files": remote_entries,
        "local_files": [],
    }
    (module_dir / "version.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class TestFasterWhisperSourceInstallable:
    def test_isinstance_installable(self):
        from sources.base import Installable
        from sources.speech.faster_whisper import FasterWhisperSource

        assert isinstance(FasterWhisperSource(), Installable)

    def test_name_attribute(self):
        from sources.speech.faster_whisper import FasterWhisperSource

        assert FasterWhisperSource().name == "faster-whisper"

    def test_default_model(self):
        from sources.speech.faster_whisper import FasterWhisperInstallParams

        assert FasterWhisperInstallParams().model == _TEST_MODEL

    def test_models_root_override_in_params(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperInstallParams

        params = FasterWhisperInstallParams(models_root=tmp_path)
        assert params.models_root == tmp_path

    def test_models_root_override_in_constructor(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperSource

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.models_root == tmp_path


class TestIsInstalled:
    def _make_params(self, tmp_path, model: str = _TEST_MODEL):
        from sources.speech.faster_whisper import FasterWhisperInstallParams

        return FasterWhisperInstallParams(model=model, models_root=tmp_path)

    def _prepared_module_dir(self, tmp_path) -> Path:
        """Create a module dir with the standard fake layout.

        Layout mirrors what ``install_fw_bundle`` would produce:
            <module_dir>/
                site-packages/        <- non-empty (wheel entry)
                    faster_whisper/__init__.py
                models/
                    config.json       <- plain remote file
        """
        from sources.speech._fw_paths import fw_module_dir

        params = self._make_params(tmp_path)
        module_dir = fw_module_dir(params)
        module_dir.mkdir(parents=True, exist_ok=True)

        # Fake wheel layout: site-packages/<pkg>/__init__.py
        site_packages = module_dir / "site-packages"
        (site_packages / "faster_whisper").mkdir(parents=True)
        (site_packages / "faster_whisper" / "__init__.py").write_bytes(b"")

        # Fake model file
        models_dir = module_dir / "models"
        models_dir.mkdir()
        (models_dir / "config.json").write_bytes(b'{"test": true}')

        return module_dir

    def test_returns_false_when_no_version_json(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperSource

        src = FasterWhisperSource(models_root=tmp_path)
        params = self._make_params(tmp_path)
        assert src.is_installed(params) is False

    def test_returns_true_when_version_json_and_all_files_present(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperSource

        module_dir = self._prepared_module_dir(tmp_path)
        _write_valid_version_json(module_dir)

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.is_installed(self._make_params(tmp_path)) is True

    def test_returns_false_when_schema_version_mismatch(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperSource

        module_dir = self._prepared_module_dir(tmp_path)
        _write_valid_version_json(module_dir, schema_version=999)

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.is_installed(self._make_params(tmp_path)) is False

    def test_returns_false_when_backend_label_wrong(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperSource

        module_dir = self._prepared_module_dir(tmp_path)
        _write_valid_version_json(module_dir, backend="whisperx")

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.is_installed(self._make_params(tmp_path)) is False

    def test_returns_false_when_model_mismatch(self, tmp_path):
        """Params asks for model X but version.json says model Y."""
        from sources.speech.faster_whisper import FasterWhisperSource

        module_dir = self._prepared_module_dir(tmp_path)
        _write_valid_version_json(module_dir, model="some/other-model")

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.is_installed(self._make_params(tmp_path)) is False

    def test_returns_false_when_plain_file_missing(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperSource

        module_dir = self._prepared_module_dir(tmp_path)
        _write_valid_version_json(module_dir)

        # Tamper: удаляем единственный plain-файл.
        (module_dir / "models/config.json").unlink()

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.is_installed(self._make_params(tmp_path)) is False

    def test_returns_false_when_wheel_dir_empty(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperSource

        module_dir = self._prepared_module_dir(tmp_path)
        _write_valid_version_json(module_dir)

        # Удаляем всё содержимое site-packages — wheel entry теперь
        # указывает на пустой каталог.
        import shutil

        shutil.rmtree(module_dir / "site-packages")
        (module_dir / "site-packages").mkdir()

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.is_installed(self._make_params(tmp_path)) is False

    def test_returns_false_when_plain_file_size_mismatch(self, tmp_path):
        from sources.speech.faster_whisper import FasterWhisperSource

        module_dir = self._prepared_module_dir(tmp_path)
        # Force payload size to 9999 which won't match actual file size.
        _write_valid_version_json(
            module_dir,
            remote_entries=[
                {
                    "logical": "faster-whisper",
                    "relpath": "site-packages",
                    "size": 0,
                    "sha256": "a" * 64,
                    "url": "https://files.pythonhosted.org/fake.whl",
                    "unpack": "wheel",
                },
                {
                    "logical": "config.json",
                    "relpath": "models/config.json",
                    "size": 9999,  # real file is 14 bytes
                    "sha256": "b" * 64,
                    "url": "https://huggingface.co/x/resolve/main/config.json",
                    "unpack": "none",
                },
            ],
        )

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.is_installed(self._make_params(tmp_path)) is False


class TestInstalledSizeBytes:
    def test_returns_zero_when_not_installed(self, tmp_path):
        from sources.speech.faster_whisper import (
            FasterWhisperInstallParams,
            FasterWhisperSource,
        )

        src = FasterWhisperSource(models_root=tmp_path)
        params = FasterWhisperInstallParams(models_root=tmp_path)
        assert src.installed_size_bytes(params) == 0

    def test_returns_positive_after_files_written(self, tmp_path):
        from sources.speech._fw_paths import fw_module_dir
        from sources.speech.faster_whisper import (
            FasterWhisperInstallParams,
            FasterWhisperSource,
        )

        params = FasterWhisperInstallParams(models_root=tmp_path)
        module_dir = fw_module_dir(params)
        module_dir.mkdir(parents=True)
        (module_dir / "fake.bin").write_bytes(b"x" * 1024)

        src = FasterWhisperSource(models_root=tmp_path)
        assert src.installed_size_bytes(params) == 1024


class TestUninstall:
    def test_uninstall_removes_module_dir(self, tmp_path):
        from sources.speech._fw_paths import fw_module_dir
        from sources.speech.faster_whisper import (
            FasterWhisperInstallParams,
            FasterWhisperSource,
        )

        params = FasterWhisperInstallParams(models_root=tmp_path)
        module_dir = fw_module_dir(params)
        module_dir.mkdir(parents=True)
        (module_dir / "version.json").write_text("{}")
        (module_dir / "models").mkdir()
        (module_dir / "models" / "config.json").write_bytes(b"{}")

        src = FasterWhisperSource(models_root=tmp_path)
        src.uninstall(params)
        assert not module_dir.exists()

    def test_uninstall_is_idempotent(self, tmp_path):
        from sources.speech.faster_whisper import (
            FasterWhisperInstallParams,
            FasterWhisperSource,
        )

        params = FasterWhisperInstallParams(models_root=tmp_path)
        src = FasterWhisperSource(models_root=tmp_path)
        src.uninstall(params)  # not installed → must not raise
        src.uninstall(params)  # and again

    def test_uninstall_only_touches_own_dir(self, tmp_path):
        """uninstall() must not touch sibling model installs.

        Tracked install invariant: каждый model получает свой каталог,
        uninstall одного не должен задеть другого.
        """
        from sources.speech._fw_paths import fw_module_dir
        from sources.speech.faster_whisper import (
            FasterWhisperInstallParams,
            FasterWhisperSource,
        )

        params_a = FasterWhisperInstallParams(
            model=_TEST_MODEL, models_root=tmp_path
        )
        params_b = FasterWhisperInstallParams(
            model="openai/whisper-medium", models_root=tmp_path
        )
        dir_a = fw_module_dir(params_a)
        dir_b = fw_module_dir(params_b)
        dir_a.mkdir(parents=True)
        dir_b.mkdir(parents=True)
        (dir_a / "marker.txt").write_text("a")
        (dir_b / "marker.txt").write_text("b")

        src = FasterWhisperSource(models_root=tmp_path)
        src.uninstall(params_a)

        assert not dir_a.exists()
        assert dir_b.exists()
        assert (dir_b / "marker.txt").read_text() == "b"


class TestPrependSitePackages:
    def test_raises_when_site_packages_missing(self, tmp_path):
        from sources.speech.faster_whisper import _prepend_site_packages

        missing = tmp_path / "nope" / "site-packages"
        with pytest.raises(RuntimeError, match="not found"):
            _prepend_site_packages(missing)

    def test_prepends_path_and_is_idempotent(self, tmp_path):
        from sources.speech.faster_whisper import _prepend_site_packages

        site_packages = tmp_path / "site-packages"
        site_packages.mkdir()
        # Save original sys.path so we can restore and avoid bleeding.
        original = list(sys.path)
        try:
            _prepend_site_packages(site_packages)
            assert sys.path[0] == str(site_packages)
            # Second call must not duplicate the entry.
            _prepend_site_packages(site_packages)
            assert sys.path.count(str(site_packages)) == 1
        finally:
            sys.path[:] = original
