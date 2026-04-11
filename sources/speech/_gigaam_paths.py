"""Пути, version.json, проверка целостности для GigaAM модуля.

Используется ТОЛЬКО из ``sources/speech/gigaam.py`` и его sibling файлов
(``_gigaam_download.py``, ``_gigaam_vad.py``). Подчёркивание в имени —
конвенциональный маркер «package-private» (см. ADR-013).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sources.speech.gigaam import GigaAMInstallParams


# При изменении bundle layout (новые файлы / переименование) — bump.
# При расхождении с установленным version.json → reinstall.
GIGAAM_SCHEMA_VERSION = 1


def default_models_root() -> Path:
    """Корневой каталог моделей для пользовательской установки.

    Windows: ``%APPDATA%/ttrpg-transcriber/models``.
    Linux/macOS: ``$XDG_DATA_HOME/ttrpg-transcriber/models`` или
    ``~/.local/share/ttrpg-transcriber/models``.
    """
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        )
    return base / "ttrpg-transcriber" / "models"


def gigaam_module_dir(params: "GigaAMInstallParams") -> Path:
    """Каталог одной установленной комбинации variant+precision.

    Layout::

        <models_root>/gigaam/<variant>-<precision>/
            encoder.onnx
            decoder.onnx
            joiner.onnx
            tokens.txt
            silero_vad.onnx
            hotwords.txt
            version.json
    """
    root = params.models_root or default_models_root()
    return root / "gigaam" / f"{params.variant.value}-{params.precision.value}"


@dataclass(frozen=True)
class VersionInfo:
    """Содержимое ``version.json`` для одной установки."""

    schema_version: int
    bundle_version: str  # semver-ish, например "2025.01-gigaam3-rnnt-fp32"
    variant: str
    precision: str
    files: dict[str, str]  # logical name → relpath ("encoder" → "encoder.onnx")
    file_sizes: dict[str, int]  # relpath → bytes (для быстрой проверки)
    file_sha256: dict[str, str]  # relpath → hex digest


def read_version_file(module_dir: Path) -> VersionInfo | None:
    """Прочитать ``version.json`` из каталога установки.

    Возвращает ``None`` если файла нет или формат некорректен — вызывающая
    сторона в таком случае считает установку отсутствующей.
    """
    vf = module_dir / "version.json"
    if not vf.is_file():
        return None
    try:
        data = json.loads(vf.read_text(encoding="utf-8"))
        return VersionInfo(
            schema_version=int(data["schema_version"]),
            bundle_version=str(data["bundle_version"]),
            variant=str(data["variant"]),
            precision=str(data["precision"]),
            files=dict(data["files"]),
            file_sizes={k: int(v) for k, v in data["file_sizes"].items()},
            file_sha256=dict(data["file_sha256"]),
        )
    except (KeyError, ValueError, json.JSONDecodeError, OSError):
        return None


def write_version_file(module_dir: Path, info: VersionInfo) -> None:
    """Записать ``version.json``.

    Пишется **последним** шагом install() как маркер «установка завершена»:
    если файл есть — установка корректна; если нет — частичная, надо
    переставлять.
    """
    module_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": info.schema_version,
        "bundle_version": info.bundle_version,
        "variant": info.variant,
        "precision": info.precision,
        "files": info.files,
        "file_sizes": info.file_sizes,
        "file_sha256": info.file_sha256,
    }
    (module_dir / "version.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Посчитать SHA256 от содержимого файла потоково."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
