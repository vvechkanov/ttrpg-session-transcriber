"""Скачивание GigaAM bundle. Без внешних зависимостей — только urllib.

Вызывается ТОЛЬКО из ``GigaAMSource.install()``.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.request import Request, urlopen

from sources.base import InstallProgress
from sources.speech._gigaam_paths import (
    GIGAAM_SCHEMA_VERSION,
    VersionInfo,
    gigaam_module_dir,
    sha256_file,
    write_version_file,
)

if TYPE_CHECKING:
    from sources.speech.gigaam import GigaAMInstallParams

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RemoteFile:
    """Описание одного файла bundle-а для скачивания."""

    url: str
    relpath: str  # имя внутри module_dir
    sha256: str  # ожидаемый hex-digest
    size: int  # ожидаемый размер в байтах (для progress)
    logical: str  # "encoder" | "decoder" | "joiner" | "tokens" | "vad"


# TTRPG-лексика для hotwords. Минимальный стартовый набор для D&D/PF2e
# на русском. Расширяется пользователем через отдельный механизм
# в будущем (YAGNI сейчас).
#
# См. spec §6.5.10: биасим на реальные произнесённые фразы, не на нотацию
# вида "1d20" — она всё равно не произносится в речи.
TTRPG_HOTWORDS: tuple[str, ...] = (
    # Кубики и броски
    "д20",
    "д6",
    "д8",
    "д10",
    "д12",
    "д100",
    "двадцатка",
    "натуральная",
    "крит",
    "криттен",
    "натурал",
    # Механика
    "спасбросок",
    "испытание",
    "инициатива",
    "концентрация",
    "преимущество",
    "помеха",
    # Классы
    "паладин",
    "паладина",
    "варвар",
    "варлок",
    "бард",
    "клирик",
    "друид",
    "чародей",
    "колдун",
    "следопыт",
    "монах",
    "рейнджер",
    # Системы
    "пасфайндер",
    "патфайндер",
    "днд",
    # TODO(python-dev): расширить до ~40-80 слов, взять из speaker_map.json
    # и общих D&D/PF2e терминов; обсудить с ml-specialist.
)


def _bundle_files(params: "GigaAMInstallParams") -> tuple[str, list[_RemoteFile]]:
    """Вернуть ``(bundle_version, files)`` для заданной комбинации.

    TODO(python-dev): актуальные URL-ы моделей GigaAM-v3 искать в:
      - sherpa-onnx docs: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/
      - HuggingFace: istupakov/gigaam-v3-onnx, Smirnov75/GigaAM-v3-sherpa-onnx
      - k2-fsa release tags: https://github.com/k2-fsa/sherpa-onnx/releases

    Silero VAD:
      - https://github.com/k2-fsa/sherpa-onnx/releases (asset silero_vad.onnx)

    Hotwords:
      - файл создаётся локально в install_gigaam_bundle из TTRPG_HOTWORDS.

    URL-ы, sha256 и sizes зафиксировать прямо в коде этой функции
    (короткий mapping-словарь); никаких remote manifest-ов.

    Пока реальные данные не заполнены — поднимаем NotImplementedError,
    чтобы install() падал явно и пользователь видел сообщение "GigaAM
    установка пока не сконфигурирована" вместо тихого no-op.
    """
    # params зарезервирован — после заполнения TODO выше будет
    # разветвление по params.variant / params.precision.
    del params
    raise NotImplementedError(
        "GigaAM bundle URLs are not configured yet. "
        "See TODO in sources/speech/_gigaam_download.py::_bundle_files. "
        "Research: istupakov/gigaam-v3-onnx, Smirnov75/GigaAM-v3-sherpa-onnx, "
        "sherpa-onnx releases (silero_vad.onnx)."
    )


def install_gigaam_bundle(
    params: "GigaAMInstallParams",
    progress: InstallProgress | None,
) -> None:
    """Идемпотентная установка GigaAM bundle.

    Flow:
        1. Резолвим список файлов через ``_bundle_files(params)``.
        2. Качаем всё во временный каталог (atomic move в конце).
        3. Проверяем sha256 каждого файла.
        4. Генерируем ``hotwords.txt`` локально.
        5. Атомарно перемещаем temp → финальный каталог.
        6. Записываем ``version.json`` **последним** — это маркер
           «installation complete». Если установка прервётся между move
           и write_version_file, ``is_installed`` вернёт False и
           ``install()`` безопасно повторится.
    """
    bundle_version, remote_files = _bundle_files(params)
    target_dir = gigaam_module_dir(params)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    total_bytes = sum(f.size for f in remote_files)
    downloaded_bytes = 0
    last_emit = 0.0
    emit_interval_sec = 0.25  # throttle прогресса

    def _notify(msg: str, extra_bytes: int = 0) -> None:
        nonlocal downloaded_bytes, last_emit
        downloaded_bytes += extra_bytes
        if progress is None:
            return
        now = time.monotonic()
        if extra_bytes == 0 or (now - last_emit) >= emit_interval_sec:
            fraction = downloaded_bytes / total_bytes if total_bytes else 0.0
            progress(min(fraction, 1.0), msg)
            last_emit = now

    with tempfile.TemporaryDirectory(
        prefix="gigaam-install-",
        dir=target_dir.parent,
    ) as tmp_str:
        tmp_dir = Path(tmp_str)
        for rf in remote_files:
            _notify(f"Скачивание {rf.relpath}...", extra_bytes=0)
            dst = tmp_dir / rf.relpath
            dst.parent.mkdir(parents=True, exist_ok=True)
            _download_with_progress(rf.url, dst, rf.size, _notify, rf.relpath)

            actual = sha256_file(dst)
            if actual != rf.sha256:
                raise RuntimeError(
                    f"SHA256 mismatch for {rf.relpath}: "
                    f"expected {rf.sha256[:16]}..., got {actual[:16]}..."
                )

        # Генерируем hotwords.txt локально (не скачиваем).
        hotwords_path = tmp_dir / "hotwords.txt"
        hotwords_path.write_text(
            "\n".join(TTRPG_HOTWORDS) + "\n",
            encoding="utf-8",
        )

        # Собираем VersionInfo
        files_map = {rf.logical: rf.relpath for rf in remote_files}
        files_map["hotwords"] = "hotwords.txt"
        sizes_map: dict[str, int] = {rf.relpath: rf.size for rf in remote_files}
        sizes_map["hotwords.txt"] = hotwords_path.stat().st_size
        sha_map: dict[str, str] = {rf.relpath: rf.sha256 for rf in remote_files}
        sha_map["hotwords.txt"] = sha256_file(hotwords_path)

        info = VersionInfo(
            schema_version=GIGAAM_SCHEMA_VERSION,
            bundle_version=bundle_version,
            variant=params.variant.value,
            precision=params.precision.value,
            files=files_map,
            file_sizes=sizes_map,
            file_sha256=sha_map,
        )

        # Атомарный swap: удалить старое, переместить tmp → target.
        # Примечание: TemporaryDirectory контекст ещё активен, поэтому
        # после move сам каталог уже не существует — контекст-менеджер
        # при выходе игнорирует FileNotFoundError.
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.move(str(tmp_dir), str(target_dir))

    # version.json пишется ПОСЛЕ перемещения — маркер completeness.
    write_version_file(target_dir, info)
    if progress is not None:
        progress(1.0, "Установка GigaAM завершена")
    logger.info("GigaAM bundle installed to %s", target_dir)


NotifyFn = Callable[[str, int], None]


def _download_with_progress(
    url: str,
    dst: Path,
    expected_size: int,
    notify: NotifyFn,
    label: str,
) -> None:
    """Скачать один файл с progress-уведомлениями.

    Аргумент ``expected_size`` оставлен для симметрии с ``_RemoteFile``
    (мы не сверяем Content-Length — sha256 после download — настоящая
    проверка), но сейчас не используется в теле функции.
    """
    del expected_size  # reserved; may be used for sanity-check in future
    req = Request(url, headers={"User-Agent": "ttrpg-transcriber-installer"})
    with urlopen(req, timeout=60) as response, dst.open("wb") as out:
        chunk_size = 1 << 16  # 64 KiB
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            notify(f"Скачивание {label}...", len(chunk))
