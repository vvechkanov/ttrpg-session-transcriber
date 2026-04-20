"""FasterWhisperSource — транскрипция через faster-whisper Python API.

Новый backend (не port). По умолчанию использует русскую модель
``bzikst/faster-whisper-large-v3-ru-podlodka``. Пишет canonical JSON
(schema v1, только required поля — ADR-8) в ``session_dir/transcripts/``.

Реализует ``Source`` + ``Installable`` Protocol (Epic A tracked install).
Все зависимости — wheel-ы pip closure и веса HF-модели — лежат строго
под ``<models_root>/faster-whisper/<model-slug>/``. На runtime-пути
первым делом ``sys.path`` получает ``<backend_dir>/site-packages``, и
только после этого импортируется сам ``faster_whisper`` — чтобы не было
коллизии с системно-установленной версией (которой у пользователя нет).
"""

from __future__ import annotations

import json
import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.ui_contract import UIConfig
from domain.annotations import SpeechSegment
from domain.speaker_map import resolve_speaker
from sources.base import InstallProgress, Source
from sources.speech._bundle_download import (
    all_files_present,
    read_version_file,
    total_installed_size,
)
from sources.speech._fw_paths import (
    FW_SCHEMA_VERSION,
    fw_model_dir,
    fw_module_dir,
    fw_site_packages,
)

logger = logging.getLogger(__name__)

# Совпадает с EXCLUDE_AUDIO_PREFIXES из scripts/wisper_launcher.py — craig*
# файлы — это сводный mix track Craig'а, его транскрибировать не нужно.
_EXCLUDE_AUDIO_PREFIXES: tuple[str, ...] = ("craig",)

_CANONICAL_SCHEMA_VERSION = 1
_SOURCE_ENGINE = "faster-whisper"

_DEFAULT_MODEL = "bzikst/faster-whisper-large-v3-ru-podlodka"


@dataclass(frozen=True)
class FasterWhisperInstallParams:
    """Параметры установки ``FasterWhisperSource``.

    Per-module dataclass (см. gigaam-v2 spec §2.3). Один и тот же объект
    используется для ``is_installed`` / ``install`` / ``uninstall`` /
    ``installed_size_bytes`` и для runtime-конструктора.

    ``model`` — это HF repo ID, ключ в :data:`FW_MODEL_BUNDLES`
    (``sources.speech._fw_models``). Разные модели (например,
    ``large-v3-ru-podlodka`` и ``medium``) получают независимые
    каталоги и устанавливаются/удаляются независимо — это цена
    изоляции wheel runtime.
    """

    model: str = _DEFAULT_MODEL
    # Корневой каталог моделей; по умолчанию — %APPDATA%/ttrpg-transcriber/models.
    # Переопределяется в тестах на tmp_path.
    models_root: Path | None = None


class FasterWhisperSource(Source):
    """Speech source на основе faster-whisper Python API."""

    name = "faster-whisper"

    #: Module UI Contract binding (ADR-016). Shared ``audio_source``
    #: template with GigaAM; the ``backend`` param selects the
    #: Whisper-specific form (model string + language + compute_type
    #: instead of variant/precision/num_threads). This attribute does
    #: NOT import anything from ``ui/``.
    ui_config = UIConfig(
        template="audio_source",
        params={
            "backend": "whisper",
            "device_options": ("cpu", "cuda"),
            "compute_type_options": ("int8", "int8_float16", "float16", "float32"),
            "show_hotwords": False,
        },
    )

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "ru",
        speaker_map: dict[str, str] | None = None,
        models_root: Path | None = None,
    ) -> None:
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.speaker_map = speaker_map or {}
        self.models_root = models_root
        # Lazy-loaded WhisperModel, cached across transcribe_track calls
        # so the 3 GB model doesn't reload per file. Populated by
        # _ensure_loaded on the first extract() / transcribe_track().
        self._wm: object | None = None

    # ---- Installable ----------------------------------------------------

    def _params_from_self(self) -> FasterWhisperInstallParams:
        """Построить ``FasterWhisperInstallParams`` из атрибутов источника.

        Используется runtime-путём (``extract()``): источник знает только
        про ``self.model`` и ``self.models_root``, а install-API требует
        dataclass-параметры.
        """
        return FasterWhisperInstallParams(
            model=self.model,
            models_root=self.models_root,
        )

    def is_installed(self, params: FasterWhisperInstallParams) -> bool:
        """Проверить корректность установки bundle-а для ``params.model``.

        Флоу идентичен ``GigaAMSource.is_installed``:
            1. Нет ``version.json`` → False.
            2. ``schema_version`` не совпадает → False (layout backend
               изменился, нужна переустановка).
            3. ``backend``/``model`` в payload расходятся с params → False.
            4. Любой remote/local файл отсутствует или неправильного
               размера → False.

        SHA256 не проверяется — дорогая операция. Install-поток уже
        проверил hash один раз перед записью ``version.json``.
        """
        module_dir = fw_module_dir(params)
        payload = read_version_file(module_dir)
        if payload is None:
            return False
        if int(payload.get("schema_version", 0)) != FW_SCHEMA_VERSION:
            return False
        if payload.get("backend") != "faster-whisper":
            return False
        if payload.get("model") != params.model:
            return False
        return all_files_present(module_dir, payload)

    def install(
        self,
        params: FasterWhisperInstallParams,
        progress: InstallProgress | None = None,
    ) -> None:
        """Скачать и установить wheel-closure + выбранную HF-модель.

        Блокирующая операция. Идемпотентна: повторный ``install()`` на
        корректную установку всё равно выполнит полный re-download;
        gating через ``is_installed`` — обязанность вызывающего кода
        (обычно ``core.backend_installers.install_backend``).
        """
        # Lazy import — _fw_download тянет urllib и zipfile; на обычном
        # runtime-пути модуль sources/ его импортировать не должен.
        from sources.speech._fw_download import install_fw_bundle

        install_fw_bundle(params, progress)

    def uninstall(self, params: FasterWhisperInstallParams) -> None:
        """Удалить установленный bundle для ``params.model``.

        Идемпотентна: no-op если каталог не существует. Удаляет весь
        backend dir целиком (site-packages, models, version.json) —
        ничего за его пределами не трогает.
        """
        from sources.speech._fw_download import uninstall_fw_bundle

        uninstall_fw_bundle(params)

    def installed_size_bytes(self, params: FasterWhisperInstallParams) -> int:
        """Суммарный размер установленных файлов в байтах.

        Возвращает 0 если каталог не существует.
        """
        return total_installed_size(fw_module_dir(params))

    # ---- Source --------------------------------------------------------

    def extract(self, session_dir: Path) -> list[SpeechSegment]:
        """Транскрибировать все аудио в ``session_dir`` через faster-whisper.

        Побочный эффект: пишет canonical JSON на каждый трек в
        ``session_dir/transcripts/<stem>.json``.
        """
        self._ensure_loaded()
        audio_files = _scan_audio_files(session_dir)
        if not audio_files:
            return []

        transcripts_dir = session_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)

        all_segments: list[SpeechSegment] = []
        for audio_path in audio_files:
            track_segments = self.transcribe_track(audio_path)
            _write_canonical_json(
                track_segments,
                transcripts_dir / f"{audio_path.stem}.json",
                source_engine=_SOURCE_ENGINE,
            )
            all_segments.extend(track_segments)

        all_segments.sort(key=lambda s: s.start)
        return all_segments

    def _ensure_loaded(self) -> None:
        """Load and cache the ``WhisperModel`` on first use.

        Subsequent :meth:`extract` / :meth:`transcribe_track` calls
        reuse the cached model — a 3 GB weights file should not
        reload per track.

        Runtime isolation:
            1. Bail with a clear message if the bundle is not
               installed.
            2. Prepend ``<backend_dir>/site-packages`` to ``sys.path``
               so ``faster_whisper`` and its transitive deps load from
               the isolated install, not the system site-packages.
            3. Point ``WhisperModel`` at the local model directory so
               it never reaches out to HF cache / internet.
        """

        if self._wm is not None:
            return
        params = self._params_from_self()
        if not self.is_installed(params):
            raise RuntimeError(
                f"faster-whisper bundle for model {self.model!r} is not "
                "installed. Run installer or "
                "FasterWhisperSource().install(params)."
            )

        _prepend_site_packages(fw_site_packages(params))

        # Lazy import — faster-whisper is an opional heavyweight.
        # After _prepend_site_packages it resolves to the backend dir.
        from faster_whisper import WhisperModel

        model_path = str(fw_model_dir(params))
        self._wm = WhisperModel(
            model_path,
            device=self.device,
            compute_type=self.compute_type,
        )

    def transcribe_track(
        self,
        audio_path: Path,
        speaker: str | None = None,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[SpeechSegment]:
        """Per-track public API for the Qt shell (Phase 6).

        Progress is derived from ``seg.end / info.duration`` — faster-
        whisper's iterator yields segments ordered by start time, so
        each emission advances monotonically towards 1.0. The loop
        polls ``should_cancel()`` between segments and returns partial
        results on cancellation.
        """

        self._ensure_loaded()
        wm = self._wm
        if wm is None:
            # Defensive: _ensure_loaded either populated self._wm or
            # raised; reaching here means someone mutated state
            # behind our back.
            raise RuntimeError("WhisperModel failed to load")

        if speaker is None:
            speaker = resolve_speaker(audio_path.stem, self.speaker_map)

        segments_iter, info = wm.transcribe(
            str(audio_path),
            language=self.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        duration = float(getattr(info, "duration", 0.0) or 0.0)
        track_segments: list[SpeechSegment] = []
        for seg in segments_iter:
            if should_cancel is not None and should_cancel():
                # Caller will get whatever we have so far — no raise.
                return track_segments

            # Фильтр шума: faster-whisper выставляет no_speech_prob > 0.6
            # на сегментах, где VAD/decoder подозревает отсутствие речи.
            no_speech_prob = getattr(seg, "no_speech_prob", 0.0) or 0.0
            if no_speech_prob > 0.6:
                continue

            text = (seg.text or "").strip()
            if not text:
                continue

            avg_logprob = getattr(seg, "avg_logprob", None)
            confidence = math.exp(avg_logprob) if avg_logprob is not None else None

            track_segments.append(
                SpeechSegment(
                    start=float(seg.start),
                    end=float(seg.end),
                    speaker=speaker,
                    text=text,
                    confidence=confidence,
                )
            )

            if on_progress is not None and duration > 0:
                on_progress(min(1.0, float(seg.end) / duration))

        if on_progress is not None:
            on_progress(1.0)

        return track_segments


def _prepend_site_packages(site_packages: Path) -> None:
    """Вставить ``site_packages`` в начало ``sys.path`` (идемпотентно).

    Вызывается прямо перед первым импортом ``faster_whisper`` на
    runtime-пути. Идемпотентно: если путь уже там — no-op (поэтому
    безопасно вызывать из каждого ``extract()``).

    Раскладка: wheel-ы распакованы generic installer-ом side-by-side
    в один каталог — faster_whisper, ctranslate2, tokenizers,
    huggingface_hub, onnxruntime, av, numpy и транзитивные deps лежат
    как обычные top-level пакеты Python. ``sys.path.insert(0, ...)``
    гарантирует, что именно эта копия выиграет resolution у возможно
    установленной системной версии.
    """
    path_str = str(site_packages)
    if not site_packages.is_dir():
        raise RuntimeError(
            f"faster-whisper site-packages not found at {path_str}. "
            "Install bundle first via FasterWhisperSource().install(params)."
        )
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
        logger.debug("Prepended %s to sys.path", path_str)


def _scan_audio_files(session_dir: Path, pattern: str = "*.flac") -> list[Path]:
    """Найти per-speaker треки в ``session_dir``.

    Port из ``scripts/wisper_launcher.py:_scan_audio_files``. Сохраняет
    тот же дефолтный паттерн ``*.flac`` и то же исключение craig-треков.
    """
    return sorted(
        p
        for p in session_dir.glob(pattern)
        if not any(
            p.stem.lower() == x or p.stem.lower().startswith(x + "-")
            for x in _EXCLUDE_AUDIO_PREFIXES
        )
    )


def _write_canonical_json(
    segments: list[SpeechSegment],
    path: Path,
    *,
    source_engine: str,
) -> None:
    """Записать canonical JSON (schema v1, только required поля — ADR-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _CANONICAL_SCHEMA_VERSION,
        "source_engine": source_engine,
        "segments": [
            {"start": s.start, "end": s.end, "text": s.text} for s in segments
        ],
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
