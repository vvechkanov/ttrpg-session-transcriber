"""Generic tracked-install helper: download → verify → atomic-move.

Единый паттерн установки для всех backend-ов (GigaAM-style ONNX bundles
и pip-wheel based backends вроде faster-whisper/whisperx). Модуль
полностью self-contained: только stdlib (``urllib``, ``hashlib``,
``shutil``, ``tempfile``, ``zipfile``, ``json``).

Design — см. Epic A (tracked install):
    * SHA256 fail-closed для каждого файла (пустой hash → install
      отказывается стартовать — packaging bug).
    * Atomic temp-dir: всё качается в ``<backend_dir>.parent/tmp_...``
      → проверяется → ``shutil.move`` на финальное место. Частичная
      установка никогда не мелькает под финальным именем.
    * ``version.json`` пишется **последним** как маркер
      «installation complete»; ``is_installed()`` в реализациях
      backend-ов должен читать version.json первым.
    * Если в ``_RemoteFile.unpack`` задано ``"wheel"`` или ``"zip"``,
      файл после download и SHA256-проверки распаковывается в
      поддиректорию (``site-packages`` для wheel) и сам архив
      удаляется. Распаковка происходит ДО ``move``, так что
      повреждённый zip не попадёт в финальный каталог.
    * Прогресс-колбэк (``InstallProgress``) вызывается по мере чтения
      байтов с throttle ``emit_interval_sec`` (0.25 сек по умолчанию).

Вызывается из GigaAM / faster-whisper / whisperx через тонкие обёртки,
которые готовят ``list[_RemoteFile]`` с pinned URL + SHA256 и
опциональный ``_LocalFile`` список (сгенерированные локально файлы
типа hotwords.txt).
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal
from urllib.request import Request, urlopen

from sources.base import InstallProgress

logger = logging.getLogger(__name__)


UnpackKind = Literal["none", "wheel", "zip"]


@dataclass(frozen=True)
class RemoteFile:
    """Один файл для скачивания (ONNX weight или Python wheel).

    Attributes:
        url: Прямой URL (HF LFS, PyPI CDN, GitHub releases).
        relpath: Относительный путь внутри корневого каталога backend-а
            КУДА кладётся результат. Для wheel с ``unpack="wheel"``
            это каталог распаковки (обычно ``"site-packages"``), сам
            ``.whl`` файл удаляется после распаковки.
        sha256: Ожидаемый hex-digest содержимого (fail-closed).
        size: Ожидаемый размер в байтах (используется для прогресс-бара
            до начала скачивания).
        logical: Человекочитаемый ярлык для логов и manifest
            (``"encoder"``, ``"faster_whisper"``, ``"torch"``).
        unpack: ``"none"`` — файл остаётся как есть в ``relpath``;
            ``"wheel"`` — zip-файл распаковывается в каталог ``relpath``
            (добавляя к уже лежащим там файлам — так wheel-ы разных
            пакетов собирают общий site-packages); ``"zip"`` — общий
            zip, распаковывается в ``relpath``.
    """

    url: str
    relpath: str
    sha256: str
    size: int
    logical: str
    unpack: UnpackKind = "none"


@dataclass(frozen=True)
class LocalFile:
    """Файл, сгенерированный локально во время install (не качается).

    Attributes:
        relpath: Путь внутри корневого каталога backend-а.
        content: Текстовое содержимое (UTF-8). Бинарные локальные
            файлы не поддерживаются — YAGNI.
        logical: Ярлык для manifest.
    """

    relpath: str
    content: str
    logical: str


@dataclass(frozen=True)
class BundleSpec:
    """Описание одного устанавливаемого bundle.

    Сюда backend-обёртка собирает всё, что нужно для install():
    имя, версию, список удалённых файлов, список локальных файлов.
    Generic installer принимает ``BundleSpec`` и не знает ничего
    про конкретный backend.
    """

    #: Человекочитаемое имя для логов и progress-сообщений.
    display_name: str
    #: Версия bundle-а (semver-ish строка); попадает в ``version.json``.
    bundle_version: str
    #: Корневой каталог, куда bundle устанавливается. Весь disk IO
    #: install-а строго ВНУТРИ этого каталога (см. Installable
    #: tracked install invariant).
    target_dir: Path
    #: Файлы для скачивания.
    remote_files: tuple[RemoteFile, ...]
    #: Локально генерируемые файлы (hotwords.txt и т.п.).
    local_files: tuple[LocalFile, ...] = ()
    #: Дополнительные поля, которые backend хочет видеть в
    #: ``version.json`` (variant, precision, model_id и т.п.).
    extra_version_fields: dict[str, str] = field(default_factory=dict)
    #: Версия схемы layout (bumped при изменении раскладки файлов).
    schema_version: int = 1


# ── Helpers (file hashing + progress throttling) ──────────────────────


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Потоковый SHA256 от содержимого файла."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


_NotifyFn = Callable[[str, int], None]


def _make_notify(
    progress: InstallProgress | None,
    total_bytes: int,
    emit_interval_sec: float = 0.25,
) -> _NotifyFn:
    """Создать throttled notify-функцию вокруг ``InstallProgress``.

    Возвращаемая функция принимает ``(message, bytes_delta)``. При
    ``bytes_delta=0`` сообщение эмитится безусловно (start of file),
    при ``bytes_delta > 0`` — только если прошло ``emit_interval_sec``
    с прошлого эмита.
    """
    state = {"downloaded": 0, "last_emit": 0.0}

    def _notify(message: str, extra_bytes: int) -> None:
        state["downloaded"] += extra_bytes
        if progress is None:
            return
        now = time.monotonic()
        if extra_bytes == 0 or (now - state["last_emit"]) >= emit_interval_sec:
            fraction = (
                state["downloaded"] / total_bytes if total_bytes else 0.0
            )
            progress(min(fraction, 1.0), message)
            state["last_emit"] = now

    return _notify


def _download_with_progress(
    url: str,
    dst: Path,
    notify: _NotifyFn,
    label: str,
) -> None:
    """Скачать один файл с progress-уведомлениями (64 KiB chunks)."""
    req = Request(url, headers={"User-Agent": "ttrpg-transcriber-installer"})
    with urlopen(req, timeout=60) as response, dst.open("wb") as out:
        chunk_size = 1 << 16  # 64 KiB
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            notify(f"Скачивание {label}...", len(chunk))


def _unpack_wheel(whl_path: Path, site_packages: Path) -> None:
    """Распаковать wheel в site-packages.

    Wheel = zip с layout::

        package_name/__init__.py
        package_name/...
        package_name-1.2.3.dist-info/METADATA
        package_name-1.2.3.dist-info/RECORD

    Мы просто extractall в ``site_packages``. Файлы из ``.dist-info``
    остаются на месте — они нужны ``importlib.metadata`` для
    определения установленных пакетов.

    ``.data/`` (scripts, headers, platlib) мы игнорируем: faster-whisper
    и его зависимости всё кладут прямо в корень wheel-а; если в будущем
    появится пакет, которому нужны scripts в отдельном месте, расширим
    здесь (YAGNI).
    """
    site_packages.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(whl_path, "r") as zf:
        zf.extractall(site_packages)


# ── Main entry point ──────────────────────────────────────────────────


def install_bundle(
    spec: BundleSpec,
    progress: InstallProgress | None,
) -> None:
    """Установить bundle согласно ``BundleSpec`` (atomic, fail-closed).

    Flow:
        1. Проверить что у каждого ``RemoteFile`` непустой SHA256
           (packaging bug guard).
        2. Создать временный каталог ``<target_dir>.parent/tmp_...``.
        3. Для каждого remote_file:
            * скачать в temp
            * проверить SHA256
            * если wheel/zip — распаковать в ``temp/<relpath>``
              и удалить архив
        4. Записать ``local_files`` в temp.
        5. Собрать ``version.json`` payload (но ещё не писать!).
        6. Атомарно: удалить старый ``target_dir``,
           ``shutil.move(temp → target_dir)``.
        7. Записать ``version.json`` ПОСЛЕДНИМ — маркер completeness.

    Raises:
        RuntimeError: при SHA256 mismatch или пустом hash.
        OSError: если target_dir.parent нельзя создать/записать.
    """
    target_dir = spec.target_dir
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    # Fail-closed SHA256 guard.
    for rf in spec.remote_files:
        if not rf.sha256:
            raise RuntimeError(
                f"SHA256 not configured for bundle entry {rf.relpath!r} "
                f"(logical={rf.logical}). This is a packaging bug — "
                f"empty hashes would allow trust-on-first-use installs."
            )

    total_bytes = sum(rf.size for rf in spec.remote_files)
    notify = _make_notify(progress, total_bytes)

    with tempfile.TemporaryDirectory(
        prefix=f"{target_dir.name}-install-",
        dir=target_dir.parent,
    ) as tmp_str:
        tmp_dir = Path(tmp_str)

        downloaded_paths: dict[str, Path] = {}  # relpath → where it landed

        for rf in spec.remote_files:
            notify(f"[{spec.display_name}] {rf.logical}...", 0)
            if rf.unpack == "none":
                dst = tmp_dir / rf.relpath
                dst.parent.mkdir(parents=True, exist_ok=True)
                _download_with_progress(rf.url, dst, notify, rf.logical)
                actual = sha256_file(dst)
                if actual != rf.sha256:
                    raise RuntimeError(
                        f"SHA256 mismatch for {rf.relpath}: "
                        f"expected {rf.sha256[:16]}..., got {actual[:16]}..."
                    )
                downloaded_paths[rf.relpath] = dst
            elif rf.unpack in ("wheel", "zip"):
                # Качаем .whl во временный файл РЯДОМ с tmp_dir (не внутри
                # tmp_dir/<relpath>, чтобы `relpath` остался каталогом
                # распаковки). Так же чисто удаляется после extractall.
                archive_path = (
                    tmp_dir / f"_archive_{rf.logical}_{Path(rf.url).name}"
                )
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                _download_with_progress(
                    rf.url, archive_path, notify, rf.logical
                )
                actual = sha256_file(archive_path)
                if actual != rf.sha256:
                    raise RuntimeError(
                        f"SHA256 mismatch for {rf.logical} "
                        f"({Path(rf.url).name}): "
                        f"expected {rf.sha256[:16]}..., got {actual[:16]}..."
                    )
                unpack_target = tmp_dir / rf.relpath
                notify(
                    f"[{spec.display_name}] распаковка {rf.logical}...", 0
                )
                _unpack_wheel(archive_path, unpack_target)
                archive_path.unlink()
                downloaded_paths[rf.relpath] = unpack_target
            else:  # pragma: no cover — защита от typos в константах
                raise RuntimeError(f"Unknown unpack kind: {rf.unpack!r}")

        # Локально генерируемые файлы (hotwords.txt и т.п.).
        for lf in spec.local_files:
            dst = tmp_dir / lf.relpath
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(lf.content, encoding="utf-8")

        # Собираем payload version.json (пишется уже в target_dir ниже).
        remote_files_meta: list[dict[str, object]] = []
        for rf in spec.remote_files:
            remote_files_meta.append(
                {
                    "logical": rf.logical,
                    "relpath": rf.relpath,
                    "size": rf.size,
                    "sha256": rf.sha256,
                    "url": rf.url,
                    "unpack": rf.unpack,
                }
            )
        local_files_meta: list[dict[str, object]] = []
        for lf in spec.local_files:
            abs_path = tmp_dir / lf.relpath
            local_files_meta.append(
                {
                    "logical": lf.logical,
                    "relpath": lf.relpath,
                    "size": abs_path.stat().st_size,
                }
            )
        version_payload = {
            "schema_version": spec.schema_version,
            "bundle_version": spec.bundle_version,
            "display_name": spec.display_name,
            "remote_files": remote_files_meta,
            "local_files": local_files_meta,
            **spec.extra_version_fields,
        }

        # Атомарный swap temp → final.
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.move(str(tmp_dir), str(target_dir))

    # version.json пишется ПОСЛЕДНИМ (completeness marker).
    _write_version_file(target_dir, version_payload)
    if progress is not None:
        progress(1.0, f"{spec.display_name}: установка завершена")
    logger.info("Bundle %r installed to %s", spec.display_name, target_dir)


def uninstall_bundle(target_dir: Path) -> None:
    """Идемпотентно удалить корневой каталог backend-а.

    Если каталога нет — no-op (контракт Installable.uninstall). Никогда
    не ходим за пределы ``target_dir``: ни сайд-эффектов с системными
    кешами, ни ``pip uninstall`` (у нас нет pip — мы всё качали
    wheel-ами напрямую).
    """
    if not target_dir.exists():
        return
    shutil.rmtree(target_dir)
    logger.info("Bundle uninstalled: %s", target_dir)


def read_version_file(target_dir: Path) -> dict | None:
    """Прочитать ``version.json`` из корневого каталога backend-а.

    Возвращает ``None`` если файла нет или JSON битый — вызывающая
    сторона трактует это как «установка отсутствует/повреждена» и
    делает переустановку через ``install_bundle``.
    """
    import json

    vf = target_dir / "version.json"
    if not vf.is_file():
        return None
    try:
        return json.loads(vf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def files_by_logical(payload: dict) -> dict[str, str]:
    """Построить ``{logical: relpath}`` из payload ``version.json``.

    Объединяет записи ``remote_files`` и ``local_files`` в один словарь,
    удобный для backend-specific кода, который хочет быстро найти файл
    по логическому имени (``"encoder"``, ``"hotwords"``).
    """
    result: dict[str, str] = {}
    for entry in payload.get("remote_files", []):
        result[entry["logical"]] = entry["relpath"]
    for entry in payload.get("local_files", []):
        result[entry["logical"]] = entry["relpath"]
    return result


def all_files_present(target_dir: Path, payload: dict) -> bool:
    """Проверить что все файлы из payload присутствуют с корректным размером.

    Быстрая структурная проверка без SHA256 (дорого). Предполагается
    что вызывающий код уже убедился, что schema_version совпадает.

    Для wheel-entries (unpack="wheel"/"zip") размер не проверяется
    (после распаковки в каталог size исходного архива не имеет
    смысла); проверяется только что каталог распаковки существует
    и непустой.
    """
    for entry in payload.get("remote_files", []):
        relpath = entry["relpath"]
        target = target_dir / relpath
        unpack = entry.get("unpack", "none")
        if unpack == "none":
            if not target.is_file():
                return False
            expected_size = int(entry.get("size") or 0)
            if expected_size > 0 and target.stat().st_size != expected_size:
                return False
        else:  # wheel / zip — relpath это каталог распаковки
            if not target.is_dir():
                return False
            if not any(target.iterdir()):
                return False
    for entry in payload.get("local_files", []):
        target = target_dir / entry["relpath"]
        if not target.is_file():
            return False
        expected_size = int(entry.get("size") or 0)
        if expected_size > 0 and target.stat().st_size != expected_size:
            return False
    return True


def total_installed_size(target_dir: Path) -> int:
    """Суммарный размер всех файлов под ``target_dir`` (рекурсивно).

    Возвращает 0 если каталог не существует. Обходит symlinks как
    файлы (``rglob("*")`` + ``is_file``), скрытые файлы считаются.
    """
    if not target_dir.exists():
        return 0
    return sum(
        p.stat().st_size for p in target_dir.rglob("*") if p.is_file()
    )


def _write_version_file(target_dir: Path, payload: dict) -> None:
    """Записать ``version.json`` (JSON with indent=2, UTF-8)."""
    import json

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "version.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
