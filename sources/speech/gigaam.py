"""GigaAMSource — русскоязычный speech backend на базе GigaAM-v3 + sherpa-onnx.

Модуль полностью самодостаточен: содержит свой Silero VAD (внутренняя
деталь), hotwords, загрузку моделей. См. ADR-013.

Реализует ``Source`` ABC и структурно ``Installable`` Protocol (из
``sources.base``). Init не загружает модель — ленивая инициализация внутри
``extract()``, чтобы импорт ``sources`` не падал на машине без весов.
"""

from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.ui_contract import UIConfig
from domain.annotations import SpeechSegment
from domain.speaker_map import resolve_speaker
from sources.base import InstallProgress, Source
from sources.speech._gigaam_paths import (
    GIGAAM_SCHEMA_VERSION,
    VersionInfo,
    gigaam_module_dir,
    read_version_file,
)

logger = logging.getLogger(__name__)

_CANONICAL_SCHEMA_VERSION = 1
_SOURCE_ENGINE = "gigaam-v3"

# Craig-треки — сводный mix от Craig-бота, их не транскрибируем.
_EXCLUDE_AUDIO_PREFIXES: tuple[str, ...] = ("craig",)


class GigaAMVariant(str, enum.Enum):
    """Вариант модели GigaAM-v3.

    ``RNNT`` — base, без встроенной ITN/пунктуации. Default для TTRPG:
    нотация бросков («двадцатка», «натуральная») сохраняется как есть.

    ``E2E_RNNT`` — со встроенной ITN и пунктуацией. Опция для
    пользователей, кто хочет готовый к чтению текст.
    """

    RNNT = "rnnt"
    E2E_RNNT = "e2e_rnnt"


class GigaAMPrecision(str, enum.Enum):
    """Precision весов модели."""

    FP32 = "fp32"  # default, ~900 MB
    INT8 = "int8"  # опция на будущее, ~250 MB


@dataclass(frozen=True)
class GigaAMInstallParams:
    """Параметры установки ``GigaAMSource``.

    Per-module dataclass (см. spec §2.3). Один и тот же объект используется
    для ``is_installed`` / ``install`` / ``installed_size_bytes`` и для
    runtime-конструктора.
    """

    variant: GigaAMVariant = GigaAMVariant.RNNT
    precision: GigaAMPrecision = GigaAMPrecision.FP32
    # Корневой каталог моделей; по умолчанию — %APPDATA%/ttrpg-transcriber/models
    # (через default_models_root()). Переопределяется в тестах на tmp_path.
    models_root: Path | None = None


@dataclass(frozen=True)
class _VadTuning:
    """Параметры Silero VAD (фиксированные от ml-specialist).

    Не часть публичного API — инкапсулирован внутри модуля.
    """

    threshold: float = 0.4
    min_silence_duration: float = 0.8
    min_speech_duration: float = 0.25
    max_speech_duration: float = 60.0
    window_size: int = 1024
    sample_rate: int = 16000
    num_threads: int = 2


class GigaAMSource(Source):
    """Speech source на базе GigaAM-v3 через sherpa-onnx runtime.

    Реализует ``Source`` + ``Installable`` (структурно через Protocol).
    Init НЕ загружает модель — ленивая инициализация в ``extract()``,
    чтобы импорт ``sources`` не падал на машине без установленных весов.
    """

    name = "gigaam"

    #: Module UI Contract binding (ADR-016). Hosts (``ui.shell``) resolve
    #: this to ``ui/templates/audio_source_template.py`` and render the
    #: module's home-card / settings panel / runtime panel. The ``params``
    #: dict tells the shared audio template which backend-specific form to
    #: render. This attribute does NOT import anything from ``ui/``.
    ui_config = UIConfig(
        template="audio_source",
        params={
            "backend": "gigaam",
            "precision_options": ("fp32", "int8"),
            "variant_options": ("rnnt", "e2e_rnnt"),
            "device_options": ("cpu", "cuda"),
            "show_hotwords": True,
        },
    )

    def __init__(
        self,
        variant: GigaAMVariant | str = GigaAMVariant.RNNT,
        precision: GigaAMPrecision | str = GigaAMPrecision.FP32,
        device: str = "cpu",  # "cpu" | "cuda"
        num_threads: int = 4,
        speaker_map: dict[str, str] | None = None,
        models_root: Path | None = None,
    ) -> None:
        self.variant = GigaAMVariant(variant)
        self.precision = GigaAMPrecision(precision)
        self.device = device
        self.num_threads = num_threads
        self.speaker_map = speaker_map or {}
        self.models_root = models_root
        self._recognizer: Any = None  # lazy, sherpa_onnx.OfflineRecognizer
        self._vad: Any = None  # lazy, sherpa_onnx.VoiceActivityDetector
        self._vad_tuning = _VadTuning()

    # ---- Installable ----------------------------------------------------

    def is_installed(self, params: GigaAMInstallParams) -> bool:
        """Быстрая проверка корректности установки без SHA256.

        Флоу (spec §4.1):
            1. Нет ``version.json`` → False.
            2. ``schema_version`` не совпадает → False (layout bundle-а
               изменился).
            3. variant/precision расходятся → False.
            4. Любой файл отсутствует или размер расходится → False.
        SHA256 не проверяется на каждом is_installed (дорого) — он
        проверяется один раз на ``install()`` перед записью version.json.
        """
        module_dir = gigaam_module_dir(params)
        info = read_version_file(module_dir)
        if info is None:
            return False
        if info.schema_version != GIGAAM_SCHEMA_VERSION:
            return False
        if info.variant != params.variant.value:
            return False
        if info.precision != params.precision.value:
            return False
        return _all_files_present(module_dir, info)

    def install(
        self,
        params: GigaAMInstallParams,
        progress: InstallProgress | None = None,
    ) -> None:
        """Скачать и установить GigaAM bundle. Блокирующая операция.

        Идемпотентна: повторный install() на корректную установку пройдёт
        через re-download (решение: is_installed gating делает вызывающий
        код, сам install() всегда честно скачивает). См. spec §4.2.
        """
        # Lazy import — _gigaam_download тянет urllib и не нужен импортёру
        # sources/ на обычном runtime-пути.
        from sources.speech._gigaam_download import install_gigaam_bundle

        install_gigaam_bundle(params, progress)

    def installed_size_bytes(self, params: GigaAMInstallParams) -> int:
        """Суммарный размер установленных файлов в байтах.

        Возвращает 0 если каталог не существует.
        """
        module_dir = gigaam_module_dir(params)
        if not module_dir.exists():
            return 0
        return sum(
            p.stat().st_size for p in module_dir.rglob("*") if p.is_file()
        )

    # ---- Source --------------------------------------------------------

    def extract(self, session_dir: Path) -> list[SpeechSegment]:
        """Транскрибировать все аудио в ``session_dir`` через GigaAM.

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
            speaker = resolve_speaker(audio_path.stem, self.speaker_map)
            track_segments = self._transcribe_track(audio_path, speaker)
            _write_canonical_json(
                track_segments,
                transcripts_dir / f"{audio_path.stem}.json",
                source_engine=_SOURCE_ENGINE,
            )
            all_segments.extend(track_segments)

        all_segments.sort(key=lambda s: s.start)
        return all_segments

    # ---- Internal ------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Ленивая загрузка recognizer + VAD при первом ``extract()``.

        Raises ``RuntimeError`` если модели не установлены — сообщение
        содержит подсказку пользователю (installer или GigaAMSource.install).
        """
        if self._recognizer is not None and self._vad is not None:
            return
        params = GigaAMInstallParams(
            variant=self.variant,
            precision=self.precision,
            models_root=self.models_root,
        )
        if not self.is_installed(params):
            raise RuntimeError(
                "GigaAM-v3 model is not installed. "
                "Run installer or GigaAMSource().install(params)."
            )
        from sources.speech._gigaam_vad import build_vad

        self._vad = build_vad(params, self._vad_tuning, self.num_threads)
        self._recognizer = _build_recognizer(params, self.device, self.num_threads)
        # Прогрев ONNX JIT — убирает 5–9 сек задержки из первого реального
        # сегмента (spec §6.5.8).
        _warmup_recognizer(self._recognizer)
        logger.info("GigaAM loaded and warmed up")

    def _transcribe_track(
        self,
        audio_path: Path,
        speaker: str | None,
    ) -> list[SpeechSegment]:
        """Обработать один per-speaker трек.

        Pipeline: 48 kHz int16 PCM → 16 kHz float32 mono → Silero VAD →
        chunked recognizer → ``list[SpeechSegment]``.

        TODO(python-dev): точный API ``sherpa_onnx.VoiceActivityDetector``
        (1.12+) — уточнить имена ``front``/``pop``/``flush``/``empty``.
        Текущий код следует контракту из spec §6, при несовпадении
        адаптировать (см. _drain_vad ниже).
        """
        import numpy as np

        samples_native, sr_native = _load_audio_int16_mono(audio_path)
        samples_16k = _resample_to_16k_float32(samples_native, sr_native)

        vad = self._vad
        vad.reset()

        segments_out: list[SpeechSegment] = []
        window = 512  # 32 ms @ 16 kHz — стандартный Silero work window
        n = len(samples_16k)

        i = 0
        while i + window <= n:
            vad.accept_waveform(samples_16k[i : i + window])
            self._drain_vad(vad, segments_out, speaker)
            i += window

        # Остаток короче window — flush финальный chunk.
        if i < n:
            tail = samples_16k[i:]
            # дополняем нулями до window чтобы sherpa-onnx VAD не
            # отбрасывал остаток (зависит от реализации, безопаснее
            # дополнить)
            padded = np.zeros(window, dtype=np.float32)
            padded[: len(tail)] = tail
            vad.accept_waveform(padded)

        # Финальный flush — вытолкнуть всё что накопилось
        _flush_vad(vad)
        self._drain_vad(vad, segments_out, speaker)

        return segments_out

    def _drain_vad(
        self,
        vad: Any,
        segments_out: list[SpeechSegment],
        speaker: str | None,
    ) -> None:
        """Слить готовые VAD-сегменты из буфера и распознать каждый.

        Контракт sherpa-onnx VAD (1.12+): ``vad.empty()`` — есть ли
        готовый сегмент, ``vad.front`` — текущий SpeechSegment (имеет
        ``samples`` float32 и ``start`` sample-offset), ``vad.pop()`` —
        убрать front.

        Если в future-версии API изменится — изолировано здесь.
        """
        while not vad.empty():
            speech = vad.front
            vad.pop()
            seg = self._recognize_segment(speech, speaker)
            if seg is not None:
                segments_out.append(seg)

    def _recognize_segment(
        self,
        speech: Any,
        speaker: str | None,
    ) -> SpeechSegment | None:
        """Распознать один VAD-сегмент, применить фильтры мусора.

        Фильтры (spec §6.5.9):
            1. Пустой/слишком короткий текст (< 2 символов) → None.
               Артефакт VAD-cut на переходных шумах.
            2. Density < 0.5 симв/сек на сегментах > 2 сек → None.
               Ловит пение/музыку которую VAD пропустил как речь.
        """
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16000, speech.samples)
        self._recognizer.decode_stream(stream)
        text = (stream.result.text or "").strip()

        if len(text) < 2:
            return None

        start_sec = speech.start / 16000.0
        duration_sec = len(speech.samples) / 16000.0
        end_sec = start_sec + duration_sec

        if duration_sec > 2.0 and (len(text) / duration_sec) < 0.5:
            logger.debug(
                "GigaAM: dropping low-density segment (%.1fs, %d chars): %r",
                duration_sec,
                len(text),
                text[:40],
            )
            return None

        return SpeechSegment(
            start=start_sec,
            end=end_sec,
            speaker=speaker,
            text=text,
            confidence=None,  # ADR-8 + spec §6 (sherpa-onnx RNNT не даёт)
        )


# ---- Module-level helpers (не экспортируются) -----------------------------


def _pick_decoding_method(hotwords_file: Path | None) -> str:
    """Выбрать decoding_method в зависимости от наличия hotwords.

    Возвращает ``"modified_beam_search"`` если hotwords файл непустой,
    иначе ``"greedy_search"``.

    Обоснование (spec §6.5.4):
        - hotwords-биасинг в sherpa-onnx работает ТОЛЬКО с
          modified_beam_search (ContextGraph требует ветвления путей).
        - modified_beam_search для NeMo transducer моделей (PR #3077)
          имеет зарегистрированный риск регрессий. RNNT устойчивее TDT,
          но не 100%.
        - Стратегия: платим цену beam search только если hotwords реально
          есть. Дефолтная установка без кастомных hotwords → greedy
          (быстрее, детерминированно, без риска PR #3077).
    """
    if hotwords_file is None:
        return "greedy_search"
    if not hotwords_file.is_file():
        return "greedy_search"
    try:
        content = hotwords_file.read_text(encoding="utf-8")
    except OSError:
        return "greedy_search"
    if not any(line.strip() for line in content.splitlines()):
        return "greedy_search"
    return "modified_beam_search"


def _detect_provider(device: str) -> str:
    """Выбрать ONNX Runtime provider с fallback CPU.

    Для ``device="cuda"`` валидируем наличие ``CUDAExecutionProvider``
    в onnxruntime. CUDA-сборка sherpa-onnx — это отдельный wheel,
    стандартный pip install sherpa-onnx даёт CPU-only. Передача
    ``provider="cuda"`` в CPU-only сборке → runtime error, поэтому detect
    обязателен.
    """
    if device != "cuda":
        return "cpu"
    try:
        import onnxruntime as ort

        if "CUDAExecutionProvider" in ort.get_available_providers():
            return "cuda"
    except ImportError:
        pass
    logger.warning(
        "CUDA requested but CUDAExecutionProvider unavailable; falling back to CPU"
    )
    return "cpu"


def _build_recognizer(
    params: GigaAMInstallParams,
    device: str,
    num_threads: int,
) -> Any:
    """Создать ``sherpa_onnx.OfflineRecognizer`` для GigaAM-v3 RNNT.

    Ключевые параметры (обоснование — spec §6.5):
        - ``model_type="nemo_transducer"`` (не ``"transducer"``!) —
          GigaAM = NeMo Conformer-RNNT.
        - ``modeling_unit="cjkchar"`` — GigaAM char-level токенайзер
          (НЕ BPE). См. §6.5.2: проверить tokens.txt формат перед
          первым запуском.
        - ``feature_dim=80`` — стандарт NeMo mel-filterbank.
        - ``decoding_method`` — условный (greedy если нет hotwords).
        - ``hotwords_score=1.5`` — sherpa-onnx default, умеренный boost.

    Изолировано в отдельной функции для mocking в тестах. Импорт
    sherpa_onnx — ленивый, чтобы unit-тесты без пакета не падали на import.
    """
    import sherpa_onnx

    module_dir = gigaam_module_dir(params)
    info = read_version_file(module_dir)
    if info is None:
        raise RuntimeError(
            f"_build_recognizer: GigaAM not installed at {module_dir}"
        )

    provider = _detect_provider(device)
    hotwords_path = module_dir / info.files["hotwords"]
    decoding_method = _pick_decoding_method(hotwords_path)

    kwargs: dict[str, Any] = dict(
        encoder=str(module_dir / info.files["encoder"]),
        decoder=str(module_dir / info.files["decoder"]),
        joiner=str(module_dir / info.files["joiner"]),
        tokens=str(module_dir / info.files["tokens"]),
        num_threads=num_threads,
        sample_rate=16000,
        feature_dim=80,
        decoding_method=decoding_method,
        max_active_paths=4,
        provider=provider,
        model_type="nemo_transducer",
        modeling_unit="cjkchar",
        debug=False,
    )
    # hotwords передаются только если реально активен beam search —
    # иначе sherpa-onnx игнорирует поля, но грязнит логи warning-ами.
    if decoding_method == "modified_beam_search":
        kwargs["hotwords_file"] = str(hotwords_path)
        kwargs["hotwords_score"] = 1.5

    logger.info(
        "GigaAM recognizer: method=%s, provider=%s, threads=%d",
        decoding_method,
        provider,
        num_threads,
    )
    return sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs)


def _warmup_recognizer(recognizer: Any) -> None:
    """Прогреть ONNX JIT одним dummy-inference на 0.5 сек тишины.

    Загрузка ONNX в память (~900 MB fp32) + ONNX Runtime JIT compilation
    графа на первом прогоне = 5–9 сек до первого результата. Прогрев
    убирает эту задержку из первого реального сегмента (spec §6.5.8).
    """
    import numpy as np

    stream = recognizer.create_stream()
    silence = np.zeros(8000, dtype=np.float32)  # 0.5 сек @ 16 kHz
    stream.accept_waveform(16000, silence)
    recognizer.decode_stream(stream)
    # stream отбрасываем, результат warmup не нужен


def _all_files_present(module_dir: Path, info: VersionInfo) -> bool:
    """Проверить что все файлы из ``file_sizes`` есть с правильным размером."""
    for relpath, expected_size in info.file_sizes.items():
        p = module_dir / relpath
        if not p.is_file():
            return False
        if expected_size > 0 and p.stat().st_size != expected_size:
            return False
    return True


def _scan_audio_files(
    session_dir: Path,
    pattern: str = "*.flac",
) -> list[Path]:
    """Найти per-speaker треки в ``session_dir``, исключая craig*."""
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
    """Записать canonical JSON (schema v1, только required поля — ADR-8).

    Идентично ``FasterWhisperSource`` для соответствия ADR-8 — разные
    backend-ы выдают один и тот же формат, merger их не различает.
    """
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


def _load_audio_int16_mono(audio_path: Path) -> tuple[Any, int]:
    """Загрузить аудиофайл как mono int16 PCM.

    Возвращает ``(samples: np.ndarray[int16], sample_rate: int)``.

    Использует ``soundfile`` (уже в dependencies проекта), принудительно
    приводя к int16 mono. Если канал > 1 — усредняем в моно.
    """
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(audio_path), dtype="int16", always_2d=True)
    # data shape: (frames, channels)
    if data.shape[1] > 1:
        # Среднее по каналам. Каст обратно к int16 с насыщением.
        mono = data.mean(axis=1).astype(np.int16)
    else:
        mono = data[:, 0]
    return mono, int(sr)


def _resample_to_16k_float32(samples_int16: Any, sr_native: int) -> Any:
    """Resample int16 → 16 kHz float32 в диапазоне [-1.0, 1.0].

    Используем ``scipy.signal.resample_poly`` (scipy уже есть в проекте),
    чтобы не тащить новую зависимость ``soxr``. После resample явный cast
    ``float64 → float32`` и нормализация ``/ 32768.0``.

    sherpa-onnx ``accept_waveform`` требует именно float32 нормализованный
    в [-1.0, 1.0] (spec §6 preamble).
    """
    import numpy as np
    from scipy.signal import resample_poly

    target_sr = 16000
    if sr_native == target_sr:
        return (samples_int16.astype(np.float32)) / 32768.0

    # Найти рациональное соотношение up/down.
    from math import gcd

    g = gcd(int(sr_native), target_sr)
    up = target_sr // g
    down = int(sr_native) // g
    resampled = resample_poly(samples_int16.astype(np.float32), up, down)
    # Нормализация — input был int16 scale, scipy сохраняет амплитуду.
    return (resampled / 32768.0).astype(np.float32)


def _flush_vad(vad: Any) -> None:
    """Финальный flush VAD буфера.

    ``vad.flush()`` подтверждён в sherpa-onnx 1.10+ (PR #1329) и
    присутствует в 1.12.35. Вызов обязателен для получения последнего
    речевого сегмента в файле — без него хвост аудио молча теряется.
    Изолировано отдельной функцией, чтобы при будущем API-сдвиге
    адаптация была в одном месте.
    """
    vad.flush()
