"""faster-whisper bundle manifest: thin wrapper over ``_bundle_download``.

Собирает ``BundleSpec`` из трёх источников:
    * :mod:`_fw_wheels` — transitive closure PyPI wheel-ов;
    * :mod:`_fw_models` — HF model files для выбранной модели;
    * ничего локально не генерирует (в отличие от GigaAM с hotwords).

Вызывается из :class:`FasterWhisperSource.install` / ``.uninstall``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sources.base import InstallProgress
from sources.speech._bundle_download import (
    BundleSpec,
    install_bundle,
    uninstall_bundle,
)
from sources.speech._fw_models import get_model_bundle
from sources.speech._fw_paths import FW_SCHEMA_VERSION, fw_module_dir
from sources.speech._fw_wheels import BUNDLE_VERSION as WHEEL_BUNDLE_VERSION
from sources.speech._fw_wheels import REMOTE_FILES as WHEEL_REMOTE_FILES

if TYPE_CHECKING:
    from sources.speech.faster_whisper import FasterWhisperInstallParams

logger = logging.getLogger(__name__)


def _build_spec(
    params: "FasterWhisperInstallParams",
) -> BundleSpec:
    """Собрать полный ``BundleSpec`` для выбранной модели.

    Wheel-ы одинаковые для всех моделей (один pinned pip closure),
    меняется только model-секция. Это значит, что две установленные
    модели (``large-v3-ru`` и ``medium``) дублируют site-packages
    каждая — это цена изоляции per-model, без неё clean uninstall
    модели разрушал бы её wheel runtime.
    """
    model_files = get_model_bundle(params.model)
    all_remote = tuple(WHEEL_REMOTE_FILES) + tuple(model_files)

    return BundleSpec(
        display_name=f"faster-whisper / {params.model}",
        bundle_version=f"{WHEEL_BUNDLE_VERSION}+{params.model}",
        target_dir=fw_module_dir(params),
        remote_files=all_remote,
        local_files=(),
        extra_version_fields={
            "backend": "faster-whisper",
            "model": params.model,
        },
        schema_version=FW_SCHEMA_VERSION,
    )


def install_fw_bundle(
    params: "FasterWhisperInstallParams",
    progress: InstallProgress | None,
) -> None:
    """Установить faster-whisper runtime + выбранную модель.

    Идемпотентна (``install_bundle`` переписывает target_dir
    атомарно через temp-каталог + finalize-with-version-json).
    Вызов на полностью установленную комбинацию всё равно выполнит
    полный reinstall; gating через ``is_installed`` — обязанность
    вызывающего кода (обычно ``core.backend_installers.install_backend``).
    """
    spec = _build_spec(params)
    install_bundle(spec, progress)


def uninstall_fw_bundle(params: "FasterWhisperInstallParams") -> None:
    """Идемпотентное удаление установленной модели + её wheel-ов.

    No-op если каталог ``fw_module_dir(params)`` не существует.
    Удаляет весь backend dir целиком (site-packages, models,
    version.json) — ничего за его пределами не трогает.
    """
    uninstall_bundle(fw_module_dir(params))
