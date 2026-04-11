"""Пути для GigaAM модуля.

Используется ТОЛЬКО из ``sources/speech/gigaam.py`` и его sibling файлов
(``_gigaam_download.py``, ``_gigaam_vad.py``). Подчёркивание в имени —
конвенциональный маркер «package-private» (см. ADR-013).

В Epic A (Installable tracked install) версия файлов bundle-а и их
целостность описываются через generic :mod:`_bundle_download` —
``read_version_file`` / ``all_files_present`` / ``files_by_logical``.
Этот модуль хранит только layout-константы и helper для общего
``default_models_root``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

# Re-export sha256_file из generic installer, чтобы старый код
# и тесты могли продолжать импортировать его из привычного места.
from sources.speech._bundle_download import sha256_file  # noqa: F401

if TYPE_CHECKING:
    from sources.speech.gigaam import GigaAMInstallParams


# При изменении bundle layout (новые файлы / переименование) — bump.
# При расхождении с установленным version.json → reinstall.
GIGAAM_SCHEMA_VERSION = 1


def _current_os_name() -> str:
    """Indirection over ``os.name`` for testability.

    Tests monkey-patch this helper instead of ``os.name`` directly —
    mutating global ``os.name`` on Windows breaks ``pathlib.Path()``
    which picks ``WindowsPath``/``PosixPath`` flavour from it at every
    instantiation (and then pytest's own error-reporting crashes with
    ``NotImplementedError: cannot instantiate 'PosixPath' on your system``).
    """
    return os.name


def default_models_root() -> Path:
    """Корневой каталог моделей для пользовательской установки.

    Windows: ``%APPDATA%/ttrpg-transcriber/models``.
    Linux/macOS: ``$XDG_DATA_HOME/ttrpg-transcriber/models`` или
    ``~/.local/share/ttrpg-transcriber/models``.

    Используется и GigaAM, и pip-wheel backends (faster-whisper,
    whisperx) как общий root под per-backend поддиректории.
    """
    if _current_os_name() == "nt":
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
            gigaam_v3_rnnt_encoder.onnx
            gigaam_v3_rnnt_decoder.onnx
            gigaam_v3_rnnt_joint.onnx
            gigaam_v3_rnnt_tokens.txt
            silero_vad.onnx
            hotwords.txt
            version.json
    """
    root = params.models_root or default_models_root()
    return root / "gigaam" / f"{params.variant.value}-{params.precision.value}"
