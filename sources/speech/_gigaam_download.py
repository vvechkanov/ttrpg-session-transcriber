"""GigaAM bundle manifest: thin wrapper over generic ``_bundle_download``.

Публичная поверхность (для тестов и ``GigaAMSource``):
    * :data:`TTRPG_HOTWORDS` — D&D/PF2e лексика для biasing.
    * :func:`_bundle_files` — возвращает ``(bundle_version, files)``
      для заданной комбинации variant+precision.
    * :func:`install_gigaam_bundle` — ``Installable.install`` реализация,
      делегирует в :func:`sources.speech._bundle_download.install_bundle`.
    * :func:`uninstall_gigaam_bundle` — ``Installable.uninstall``
      реализация, делегирует в
      :func:`sources.speech._bundle_download.uninstall_bundle`.

Исторический импорт ``_RemoteFile`` — теперь alias на
:class:`sources.speech._bundle_download.RemoteFile`, чтобы тесты
продолжали импортировать его из этого модуля.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sources.base import InstallProgress
from sources.speech._bundle_download import (
    BundleSpec,
    LocalFile,
    RemoteFile,
    install_bundle,
    uninstall_bundle,
)
from sources.speech._gigaam_paths import (
    GIGAAM_SCHEMA_VERSION,
    gigaam_module_dir,
)

if TYPE_CHECKING:
    from sources.speech.gigaam import GigaAMInstallParams

logger = logging.getLogger(__name__)

#: Backward-compatible alias. Старое имя использовали тесты
#: (``from sources.speech._gigaam_download import _RemoteFile``).
#: Структурно идентичен новому ``RemoteFile`` — tests не замечают разницы.
_RemoteFile = RemoteFile


# TTRPG-лексика для hotwords. Минимальный стартовый набор для D&D/PF2e
# на русском. Расширяется пользователем через отдельный механизм
# в будущем (YAGNI сейчас).
#
# См. spec §6.5.10: биасим на реальные произнесённые фразы, не на нотацию
# вида "1d20" — она всё равно не произносится в речи.
TTRPG_HOTWORDS: tuple[str, ...] = (
    # Кубики и броски
    "д20", "д6", "д8", "д10", "д12", "д100",
    "двадцатка", "натуральная", "натуралка", "натурал",
    "крит", "криттен", "критует", "провал",
    # Механика
    "спасбросок", "спасброска", "испытание",
    "инициатива", "инициативу",
    "концентрация", "концентрацию",
    "преимущество", "помеха",
    "проверка", "проверку", "сложность",
    "модификатор", "бонус", "мастерства",
    # Боевые термины
    "кд", "класс брони", "хиты", "хитпоинты", "хитов",
    "урон", "урона", "атака", "атаку",
    "реакция", "реакцию", "бонусное", "действие", "движение",
    # Классы
    "паладин", "паладина", "варвар", "варвара",
    "варлок", "варлока", "бард",
    "клирик", "жрец", "друид",
    "чародей", "колдун",
    "следопыт", "рейнджер", "монах",
    "плут", "файтер", "волшебник",
    "изобретатель", "артифайсер",
    # Заклинания
    "огненный шар", "файербол",
    "лечение ран", "щит",
    "волшебная стрела", "благословение", "молния",
    # Расы
    "эльф", "дварф", "полурослик",
    "тифлинг", "тифлинга",
    "драконорождённый", "полуорк",
    # Системы
    "пасфайндер", "патфайндер", "пасфайндера", "днд",
    # PF2e специфика
    "ступень", "фокус",
    "тренированный", "опытный", "легендарный",
    # Ролевые термины
    "мастер", "гейммастер", "гм",
    "игрок", "персонаж", "нпс", "нпц",
)


def _bundle_files(
    params: "GigaAMInstallParams",
) -> tuple[str, list[RemoteFile]]:
    """Вернуть ``(bundle_version, remote_files)`` для заданной комбинации.

    Реальные данные для rnnt+fp32 из HF репо
    ``Smirnov75/GigaAM-v3-sherpa-onnx``. Другие комбинации (e2e, int8)
    пока не сконфигурированы — NotImplementedError.

    Hotwords файл создаётся локально в ``install_gigaam_bundle`` из
    :data:`TTRPG_HOTWORDS` — он НЕ входит в список ``remote_files``,
    это отдельный ``LocalFile`` в ``BundleSpec``.
    """
    from sources.speech.gigaam import GigaAMPrecision, GigaAMVariant

    if (
        params.variant != GigaAMVariant.RNNT
        or params.precision != GigaAMPrecision.FP32
    ):
        raise NotImplementedError(
            f"GigaAM bundle for variant={params.variant.value}, "
            f"precision={params.precision.value} is not configured yet. "
            f"Only rnnt+fp32 is currently supported."
        )

    bundle_version = "v3-rnnt-fp32-smirnov75"
    base = "https://huggingface.co/Smirnov75/GigaAM-v3-sherpa-onnx/resolve/main"
    files = [
        RemoteFile(
            url=f"{base}/gigaam_v3_rnnt_encoder.onnx",
            relpath="gigaam_v3_rnnt_encoder.onnx",
            # SHA256 from HF LFS oid; verify after first download.
            sha256="ca20f0a6e0e46ba770b87c6592cbdc5b8a96307c40c83ecdd33c6588415c7a19",
            size=885084896,
            logical="encoder",
        ),
        RemoteFile(
            url=f"{base}/gigaam_v3_rnnt_decoder.onnx",
            relpath="gigaam_v3_rnnt_decoder.onnx",
            sha256="633ef97f2c6c9ca11c91b6c7ee8f6054fc7a964e6b22d7a904fd096b458f0308",
            size=3331577,
            logical="decoder",
        ),
        RemoteFile(
            url=f"{base}/gigaam_v3_rnnt_joint.onnx",
            relpath="gigaam_v3_rnnt_joint.onnx",
            sha256="fd1d02f45c2ad3d6b67cc149811ad794ab4b020ed49a0a9e2790a8619d1cddd8",
            size=1440448,
            logical="joiner",
        ),
        RemoteFile(
            url=f"{base}/gigaam_v3_rnnt_tokens.txt",
            relpath="gigaam_v3_rnnt_tokens.txt",
            # 195-byte git blob (not LFS), 34 tokens: space(0) + а-я без ё
            # (1-32) + <blk>(33). NOTE: GigaAM-v3 tokenizer does NOT include
            # "ё" — model collapses ё→е at training time (known upstream
            # behaviour). Hash from one-time bootstrap download (2026-04-11).
            sha256="48c9111eb77c9c42d08ecc71c00c09407ef2cce01195d72b7cc0c3c08ce89213",
            size=195,
            logical="tokens",
        ),
        RemoteFile(
            url="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
            relpath="silero_vad.onnx",
            # Hash from one-time bootstrap download (2026-04-11).
            # NB: if k2-fsa re-releases this asset under the rolling
            # `asr-models` tag, this hash will mismatch — that's intentional
            # fail-closed behaviour; bump hash only after manual verification.
            sha256="9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6",
            size=643854,
            logical="vad",
        ),
    ]
    return bundle_version, files


def install_gigaam_bundle(
    params: "GigaAMInstallParams",
    progress: InstallProgress | None,
) -> None:
    """Идемпотентная установка GigaAM bundle.

    Делегирует в generic :func:`install_bundle`, прокидывая список
    удалённых ONNX-файлов и локально генерируемый ``hotwords.txt``.
    Атомарность, SHA256 verification и порядок записи ``version.json``
    обеспечивает generic installer.
    """
    bundle_version, remote_files = _bundle_files(params)
    target_dir = gigaam_module_dir(params)
    hotwords_content = "\n".join(TTRPG_HOTWORDS) + "\n"

    spec = BundleSpec(
        display_name="GigaAM-v3",
        bundle_version=bundle_version,
        target_dir=target_dir,
        remote_files=tuple(remote_files),
        local_files=(
            LocalFile(
                relpath="hotwords.txt",
                content=hotwords_content,
                logical="hotwords",
            ),
        ),
        extra_version_fields={
            "variant": params.variant.value,
            "precision": params.precision.value,
        },
        schema_version=GIGAAM_SCHEMA_VERSION,
    )
    install_bundle(spec, progress)


def uninstall_gigaam_bundle(params: "GigaAMInstallParams") -> None:
    """Идемпотентное удаление GigaAM bundle.

    Удаляет весь каталог ``<models_root>/gigaam/<variant>-<precision>/``.
    No-op если каталог не существует.
    """
    uninstall_bundle(gigaam_module_dir(params))
