"""Core shim over ``Installable`` sources.

Даёт UI-слою (``ui/cli.py``, ``ui/gui.py``, ``launcher/installer_ui.py``)
тонкую backend-agnostic ручку для установки моделей, НЕ раскрывая конкретные
типы из ``sources/`` наружу UI. Dependency rules (``ARCHITECTURE.md §3``)
запрещают ``ui → sources``, поэтому всё идёт через этот шим.

См. ``docs/specs/gigaam-v2.md`` §5.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from sources.base import Installable, InstallProgress
from sources.speech.gigaam import (
    GigaAMInstallParams,
    GigaAMPrecision,
    GigaAMSource,
    GigaAMVariant,
)


class BackendId(str, enum.Enum):
    """Идентификаторы установщиков, которые знает UI."""

    GIGAAM_RNNT_FP32 = "gigaam-rnnt-fp32"
    # Будущее: GIGAAM_E2E_RNNT_FP32, GIGAAM_RNNT_INT8 и т.д.


@dataclass(frozen=True)
class BackendInfo:
    """Метаданные для отображения в GUI / installer wizard."""

    id: BackendId
    title: str  # "GigaAM-v3 RNNT (русский)"
    description: str  # "~900 MB. RNNT без встроенной пунктуации..."
    approx_download_bytes: int  # для прогресс-бара до начала установки
    default_selected: bool  # checkbox по умолчанию в wizard


# Hardcoded registry — в стиле SPEECH_SOURCES (ADR-11).
#
# Примечание: ``default_selected=False`` пока ``_bundle_files`` не заполнен
# реальными URL — см. TODO(python-dev) в
# ``sources/speech/_gigaam_download.py::_bundle_files``. Когда URL появятся,
# поменять на ``True`` согласно gigaam-v2.md §5.
BACKENDS: dict[BackendId, BackendInfo] = {
    BackendId.GIGAAM_RNNT_FP32: BackendInfo(
        id=BackendId.GIGAAM_RNNT_FP32,
        title="GigaAM-v3 RNNT (русский)",
        description=(
            "Русскоязычный ASR для TTRPG. ~900 MB. Без встроенной "
            "пунктуации — терминология бросков и характеристик "
            "сохраняется как есть. [Установка пока недоступна — см. TODO]"
        ),
        approx_download_bytes=950_000_000,
        default_selected=False,
    ),
}


def list_backends() -> list[BackendInfo]:
    """Вернуть список всех известных UI backend-ов."""
    return list(BACKENDS.values())


def is_backend_installed(backend_id: BackendId) -> bool:
    """Проверить что bundle для указанного backend-а уже установлен."""
    source, params = _resolve(backend_id)
    return source.is_installed(params)


def installed_size_bytes(backend_id: BackendId) -> int:
    """Вернуть занимаемое место на диске для указанного backend-а."""
    source, params = _resolve(backend_id)
    return source.installed_size_bytes(params)


def install_backend(
    backend_id: BackendId,
    progress: InstallProgress | None = None,
) -> None:
    """Блокирующая установка. Вызывается из worker-thread UI-клиентами.

    Сам метод НЕ поднимает поток. Клиент (``ui/gui.py`` modal, installer
    wizard) обязан завернуть вызов в ``threading.Thread`` или executor.
    """
    source, params = _resolve(backend_id)
    source.install(params, progress=progress)


def _resolve(backend_id: BackendId) -> tuple[Installable, object]:
    """Вернуть ``(source, params)`` для указанного backend-а.

    Единственная точка в проекте, где UI-facing BackendId конвертируется
    в конкретный класс sources/. Расширение: добавить новый ``if`` здесь
    и запись в ``BACKENDS``.
    """
    if backend_id == BackendId.GIGAAM_RNNT_FP32:
        source = GigaAMSource(
            variant=GigaAMVariant.RNNT,
            precision=GigaAMPrecision.FP32,
        )
        params = GigaAMInstallParams(
            variant=GigaAMVariant.RNNT,
            precision=GigaAMPrecision.FP32,
        )
        return source, params
    raise ValueError(f"unknown backend: {backend_id}")
