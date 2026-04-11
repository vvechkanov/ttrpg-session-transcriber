# Спецификация v2 (merged): модуль `GigaAMSource` (sherpa-onnx + GigaAM-v3)

**Адресат:** `python-dev` (реализация), `qa-engineer` (тесты)
**Контекст:** P2 рефакторинг завершён, шестислойная архитектура в силе. Этот спек добавляет второй speech backend в `sources/speech/` без нарушения слоёв.
**Статус constraints:** все 10 пунктов от пользователя приняты как зафиксированные решения.

**Источник:** этот документ объединяет:
- архитектурный спек v2 от агента `architect` (структура слоёв, `Installable` contract, интеграция с installer_ui/gui);
- runtime-параметры `OfflineRecognizer` + обоснования от агента `ml-specialist` (параметры sherpa-onnx, conditional decoding, warmup, фильтры).

Все конфликты разрешены в пользу ml-specialist для runtime-параметров и в пользу architect для слоёв/контрактов. См. **§6.5 «Runtime params — обоснование»** для ссылок на источники.

**Минимальная версия `sherpa-onnx`:** `>=1.12.0,<2.0` — обязательно. До 1.12 (PR #3077, февраль 2026) hotwords-биасинг для NeMo transducer моделей не работает. См. §6.5.

---

## 1. Файловая структура нового кода

```
sources/
  base.py                              # + Installable Protocol + InstallProgress type
  __init__.py                          # + GigaAMSource в SPEECH_SOURCES
  speech/
    gigaam.py                          # NEW: GigaAMSource, GigaAMVariant, GigaAMInstallParams
    _gigaam_paths.py                   # NEW: каталоги, version.json, hash utils
    _gigaam_download.py                # NEW: download + progress (urllib)
    _gigaam_vad.py                     # NEW: internal VAD wrapper (silero)

core/
  backend_installers.py                # NEW: UI-facing shim поверх Installable
  pipeline.py                          # MOD: _speech_kwargs для GigaAMSource
  app_dirs.py                          # NEW (если ещё нет): %APPDATA%/ttrpg-transcriber

ui/
  cli.py                               # MOD: --speech_backend gigaam, --gigaam_variant
  gui.py                               # MOD: dropdown + lazy-install modal

launcher/
  installer_ui.py                      # MOD: checkbox "Установить GigaAM-v3 (русский)"

scripts/
  download_gigaam.py                   # NEW: dev/CI обёртка — тонкая

docs/adr/
  ADR-013-gigaam-independent-module.md # NEW
```

**Правило приватности:** файлы `_gigaam_*.py` не экспортируются из `sources/__init__.py` и не импортируются ничем кроме `sources/speech/gigaam.py`. Подчёркивание — конвенциональный маркер «package-private».

---

## 2. Контракт `Installable` — расположение и форма

### 2.1 Куда положить

**Решение:** `sources/base.py`, рядом с `Source`.

**Обоснование:** `Installable` — это характеристика конкретных реализаций `Source` (не всех: `FvttChatSource` установки не требует). Нет смысла создавать отдельный модуль ради одного Protocol. `sources/base.py` уже публичный, уже импортируется `sources/__init__.py`.

### 2.2 Форма — `Protocol`, не `ABC`

**Решение:** `typing.Protocol` с `@runtime_checkable`. Не `ABC`.

**Обоснование:**
- `Source` — это ABC (наследование обязательно для регистрации в `SPEECH_SOURCES`). `Installable` — это ортогональная способность. Multiple inheritance от двух ABC создаёт MRO-проблемы без пользы.
- Protocol позволяет структурную типизацию: `core.backend_installers` принимает `Installable`, и любой source который случайно реализует методы — проходит. Это упрощает unit-тесты (fake objects без наследования).
- `runtime_checkable` позволяет `isinstance(src, Installable)` для фильтрации в `SPEECH_SOURCES` (нужно в GUI/installer — показывать чекбоксы только для Installable source-ов).

### 2.3 `InstallParams` — per-module dataclass, не базовый тип

**Решение:** каждый Installable source определяет свой frozen dataclass. Никакого базового `InstallParams` или Protocol.

**Обоснование:** параметры установки у разных backend-ов принципиально разные (GigaAM имеет variant/precision, будущий модуль эмоций — совсем другое). Попытка ввести общий тип приведёт либо к stringly-typed bag `dict[str, Any]`, либо к пустому Protocol без полей. Ни то ни другое не даёт помощи типизатора. Шим `core.backend_installers` знает конкретные типы и поэтому дёргает правильные поля.

### 2.4 Сигнатура

```python
# sources/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from domain.annotations import Annotation


class Source(ABC):
    name: str

    @abstractmethod
    def extract(self, session_dir: Path) -> list[Annotation]: ...


# Progress callback: (fraction_0_to_1, human_readable_message) -> None
# - Вызывается из worker-thread. UI-клиент обязан сам пробрасывать
#   результаты в main-thread (через queue/after).
# - Throttling — обязанность ВЫЗЫВАЮЩЕЙ стороны (того кто дёргает .install()),
#   а не Installable.install(). Source может вызывать callback часто.
#   См. §5.3.
InstallProgress = Callable[[float, str], None]


@runtime_checkable
class Installable(Protocol):
    """Способность source-а устанавливать свои runtime-зависимости (модели,
    вспомогательные файлы) в пользовательский каталог.

    Реализации ДОЛЖНЫ быть идемпотентными: повторный install() на корректно
    установленную версию — no-op (быстрая проверка через is_installed).
    Некорректная/частичная установка восстанавливается install()-ом без
    отдельного repair()/upgrade().

    Параметры установки (params) — per-module dataclass. Вызывающая сторона
    (core.backend_installers) знает конкретный тип.
    """

    def is_installed(self, params: object) -> bool: ...

    def install(
        self,
        params: object,
        progress: InstallProgress | None = None,
    ) -> None: ...

    def installed_size_bytes(self, params: object) -> int:
        """Суммарный размер установленных файлов в байтах.

        Если не установлено — возвращает 0. Используется Settings → Models
        панелью (P?, YAGNI сейчас) для отображения «занимаемое место».
        Контракт включён заранее, чтобы не ломать совместимость при добавлении
        панели.
        """
        ...
```

**Про `params: object`:** Protocol не может параметризоваться по конкретному dataclass без TypeVar, а TypeVar-ы на Protocol создают проблемы с variance. Решение: тип `object` на уровне Protocol, конкретный `GigaAMInstallParams` в реальной сигнатуре `GigaAMSource.install(self, params: GigaAMInstallParams, ...)`. Mypy примет это как valid Protocol implementation благодаря структурной типизации. Шим в `core.backend_installers` работает с конкретными типами — type-safe.

---

## 3. Публичный API модуля `sources/speech/gigaam.py`

```python
"""GigaAMSource — русскоязычный speech backend на базе GigaAM-v3 + sherpa-onnx.

Модуль полностью самодостаточен: содержит свой Silero VAD (внутренняя
деталь), hotwords, загрузку моделей. См. ADR-013.
"""

from __future__ import annotations

import enum
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from domain.annotations import SpeechSegment
from domain.speaker_map import resolve_speaker
from sources.base import InstallProgress, Source
from sources.speech._gigaam_paths import (
    GIGAAM_SCHEMA_VERSION,
    VersionInfo,
    gigaam_module_dir,
    read_version_file,
    write_version_file,
)

logger = logging.getLogger(__name__)

_CANONICAL_SCHEMA_VERSION = 1
_SOURCE_ENGINE = "gigaam-v3"

_EXCLUDE_AUDIO_PREFIXES: tuple[str, ...] = ("craig",)


class GigaAMVariant(str, enum.Enum):
    """Вариант модели GigaAM-v3.

    RNNT  — base, без встроенной ITN/пунктуации. Default для TTRPG,
            чтобы '1d20' не превращалось в 'один-дэ-двадцать'.
    E2E_RNNT — со встроенной ITN и пунктуацией. Опционально для
               пользователей кто хочет готовый к чтению текст.
    """

    RNNT = "rnnt"
    E2E_RNNT = "e2e_rnnt"


class GigaAMPrecision(str, enum.Enum):
    """Precision весов модели."""

    FP32 = "fp32"   # default, ~900 MB
    INT8 = "int8"   # опция на будущее, ~250 MB


@dataclass(frozen=True)
class GigaAMInstallParams:
    """Параметры установки GigaAMSource.

    Per-module dataclass (см. §2.3). Один и тот же объект используется
    для is_installed/install/installed_size_bytes/runtime-конструктора.
    """

    variant: GigaAMVariant = GigaAMVariant.RNNT
    precision: GigaAMPrecision = GigaAMPrecision.FP32
    # Путь к каталогу моделей верхнего уровня; по умолчанию
    # %APPDATA%/ttrpg-transcriber/models. Переопределяется в тестах.
    models_root: Path | None = None


@dataclass(frozen=True)
class _VadTuning:
    """Параметры Silero VAD (фиксированные от ml-specialist). Не часть
    публичного API — инкапсулирован внутри модуля.
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

    Реализует Source + Installable (структурно, через Protocol).

    Init НЕ загружает модель — ленивая инициализация в extract() чтобы
    импорт ``sources`` не падал на машине без установленных весов.
    """

    name = "gigaam"

    def __init__(
        self,
        variant: GigaAMVariant | str = GigaAMVariant.RNNT,
        precision: GigaAMPrecision | str = GigaAMPrecision.FP32,
        device: str = "cpu",              # "cpu" | "cuda"
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
        self._recognizer = None   # lazy
        self._vad = None          # lazy
        self._vad_tuning = _VadTuning()

    # ---- Installable ----------------------------------------------------

    def is_installed(self, params: GigaAMInstallParams) -> bool:
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
        # Все объявленные файлы должны существовать с правильным размером
        return _all_files_present(module_dir, info)

    def install(
        self,
        params: GigaAMInstallParams,
        progress: InstallProgress | None = None,
    ) -> None:
        from sources.speech._gigaam_download import install_gigaam_bundle
        install_gigaam_bundle(params, progress)

    def installed_size_bytes(self, params: GigaAMInstallParams) -> int:
        module_dir = gigaam_module_dir(params)
        if not module_dir.exists():
            return 0
        return sum(
            p.stat().st_size
            for p in module_dir.rglob("*")
            if p.is_file()
        )

    # ---- Source --------------------------------------------------------

    def extract(self, session_dir: Path) -> list[SpeechSegment]:
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
        # сегмента. См. _warmup_recognizer().
        _warmup_recognizer(self._recognizer)
        logger.info("GigaAM loaded and warmed up")

    def _transcribe_track(
        self,
        audio_path: Path,
        speaker: str | None,
    ) -> list[SpeechSegment]:
        """Pipeline для одного per-speaker трека:
        48 kHz PCM → 16 kHz mono → Silero VAD → chunk → recognizer → SpeechSegment.

        Подробности — в §6 спека, реализация — TODO(python-dev).
        """
        ...


# ---- Module-level helpers (не экспортируются) -----------------------------

def _pick_decoding_method(hotwords_file: Path | None) -> str:
    """Выбрать decoding_method: modified_beam_search если есть непустой hotwords
    файл, иначе greedy_search.

    Обоснование (см. §6.5):
    - hotwords-биасинг в sherpa-onnx работает ТОЛЬКО с modified_beam_search
      (ContextGraph требует ветвления путей).
    - modified_beam_search для NeMo transducer моделей (PR #3077) имеет
      зарегистрированный риск регрессий (~20% galls/empty на NeMo TDT;
      для RNNT меньше но не ноль).
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

    Для "cuda" валидируем наличие CUDAExecutionProvider в онхрайме — CUDA-сборка
    sherpa-onnx это отдельный wheel (`sherpa-onnx==X.Y+cuda`), стандартный
    pip install sherpa-onnx даёт CPU-only. Передача provider="cuda" в
    CPU-only сборке → runtime error, поэтому detect обязателен.
    """
    if device != "cuda":
        return "cpu"
    try:
        import onnxruntime as ort
        if "CUDAExecutionProvider" in ort.get_available_providers():
            return "cuda"
    except ImportError:
        pass
    logger.warning("CUDA requested but CUDAExecutionProvider unavailable; falling back to CPU")
    return "cpu"


def _build_recognizer(params, device: str, num_threads: int):
    """Создать sherpa_onnx.OfflineRecognizer для GigaAM-v3 RNNT.

    Ключевые параметры (см. §6.5 за обоснованиями):
      - model_type="nemo_transducer" (не "transducer"!)  ← GigaAM = NeMo Conformer-RNNT
      - modeling_unit="cjkchar"  ← GigaAM char-level токенайзер (НЕ BPE)
      - feature_dim=80  ← стандарт NeMo mel-filterbank
      - decoding_method: условный (greedy если нет hotwords)
      - hotwords_score=1.5 (sherpa-onnx default, умеренный boost)
      - max_active_paths=4 (default; больше не даёт прироста на char-level)

    Изолировано в отдельной функции для мокания в тестах.
    Импорт sherpa_onnx внутри функции — ленивый (чтобы unit-тесты без
    sherpa_onnx не падали на import).
    """
    import sherpa_onnx
    from sources.speech._gigaam_paths import gigaam_module_dir

    module_dir = gigaam_module_dir(params)
    info = read_version_file(module_dir)
    assert info is not None

    provider = _detect_provider(device)
    hotwords_path = module_dir / info.files["hotwords"]
    decoding_method = _pick_decoding_method(hotwords_path)

    kwargs = dict(
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
    # hotwords передаём только если реально включён beam search,
    # иначе sherpa-onnx игнорирует эти поля но грязнит логи.
    if decoding_method == "modified_beam_search":
        kwargs["hotwords_file"] = str(hotwords_path)
        kwargs["hotwords_score"] = 1.5

    logger.info(
        "GigaAM recognizer: method=%s, provider=%s, threads=%d",
        decoding_method, provider, num_threads,
    )
    return sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs)


def _warmup_recognizer(recognizer) -> None:
    """Прогреть ONNX JIT одним dummy-inference на 0.5 сек тишины.

    Загрузка ONNX модели + ONNX Runtime JIT compilation графа при первом
    прогоне = 5–9 сек на типовом десктопе. Прогрев убирает эту задержку
    из первого реального сегмента, что критично для UX «нажал Start →
    что-то происходит сразу».
    """
    import numpy as np
    stream = recognizer.create_stream()
    silence = np.zeros(8000, dtype=np.float32)  # 0.5 сек @ 16 kHz
    stream.accept_waveform(16000, silence)
    recognizer.decode_stream(stream)
    # stream отбрасываем, результат warmup не нужен


def _all_files_present(module_dir: Path, info: VersionInfo) -> bool:
    for relpath, expected_size in info.file_sizes.items():
        p = module_dir / relpath
        if not p.is_file():
            return False
        if expected_size > 0 and p.stat().st_size != expected_size:
            return False
    return True


def _scan_audio_files(session_dir: Path, pattern: str = "*.flac") -> list[Path]:
    return sorted(
        p for p in session_dir.glob(pattern)
        if not any(
            p.stem.lower() == x or p.stem.lower().startswith(x + "-")
            for x in _EXCLUDE_AUDIO_PREFIXES
        )
    )


def _write_canonical_json(segments, path: Path, *, source_engine: str) -> None:
    # Идентично FasterWhisperSource для соответствия ADR-8.
    import json
    payload = {
        "schema_version": _CANONICAL_SCHEMA_VERSION,
        "source_engine": source_engine,
        "segments": [
            {"start": s.start, "end": s.end, "text": s.text} for s in segments
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
```

---

## 4. Внутренние модули

### 4.1 `sources/speech/_gigaam_paths.py`

```python
"""Пути, version.json, проверка целостности для GigaAM модуля.

Используется ТОЛЬКО из sources/speech/gigaam.py и его sibling файлов.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

# При изменении bundle layout (новые файлы / переименование) — bump.
# При расхождении с установленным version.json → reinstall.
GIGAAM_SCHEMA_VERSION = 1


def default_models_root() -> Path:
    """%APPDATA%/ttrpg-transcriber/models на Windows, иначе ~/.local/share/."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        )
    return base / "ttrpg-transcriber" / "models"


def gigaam_module_dir(params) -> Path:
    """Каталог одной установленной комбинации variant+precision.

    Layout:
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
    """Содержимое version.json."""
    schema_version: int
    bundle_version: str      # semver-ish, e.g. "2025.01-gigaam3-rnnt"
    variant: str
    precision: str
    files: dict[str, str]    # logical name → relpath ("encoder" → "encoder.onnx")
    file_sizes: dict[str, int]   # relpath → bytes (для быстрой проверки)
    file_sha256: dict[str, str]  # relpath → hex digest


def read_version_file(module_dir: Path) -> VersionInfo | None:
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
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def write_version_file(module_dir: Path, info: VersionInfo) -> None:
    (module_dir / "version.json").write_text(
        json.dumps(
            {
                "schema_version": info.schema_version,
                "bundle_version": info.bundle_version,
                "variant": info.variant,
                "precision": info.precision,
                "files": info.files,
                "file_sizes": info.file_sizes,
                "file_sha256": info.file_sha256,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
```

**Формат `version.json`:**

```json
{
  "schema_version": 1,
  "bundle_version": "2025.01-gigaam3-rnnt-fp32",
  "variant": "rnnt",
  "precision": "fp32",
  "files": {
    "encoder": "encoder.onnx",
    "decoder": "decoder.onnx",
    "joiner":  "joiner.onnx",
    "tokens":  "tokens.txt",
    "vad":     "silero_vad.onnx",
    "hotwords":"hotwords.txt"
  },
  "file_sizes": {
    "encoder.onnx": 450000000,
    "...": 0
  },
  "file_sha256": {
    "encoder.onnx": "abc123...",
    "...": ""
  }
}
```

**Политика сравнения версий (is_installed):**

1. `version.json` отсутствует → not installed.
2. `schema_version` ≠ `GIGAAM_SCHEMA_VERSION` → not installed (bundle layout изменился).
3. `variant`/`precision` ≠ запрошенному → not installed.
4. Любой файл отсутствует или размер расходится → not installed.
5. SHA256 **не проверяется на каждом is_installed** (дорого) — только в конце install() один раз, перед записью version.json. Runtime-детекция порчи файлов — не задача этого уровня.

---

### 4.2 `sources/speech/_gigaam_download.py`

```python
"""Скачивание GigaAM bundle. Без внешних зависимостей — только urllib.

Вызывается ТОЛЬКО из GigaAMSource.install().
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

from sources.base import InstallProgress
from sources.speech._gigaam_paths import (
    GIGAAM_SCHEMA_VERSION,
    VersionInfo,
    gigaam_module_dir,
    sha256_file,
    write_version_file,
)


@dataclass(frozen=True)
class _RemoteFile:
    url: str
    relpath: str           # имя внутри module_dir
    sha256: str            # ожидаемый хэш
    size: int              # ожидаемый размер в байтах (для progress)
    logical: str           # "encoder" | "decoder" | ...


def _bundle_files(params) -> tuple[str, list[_RemoteFile]]:
    """Вернуть (bundle_version, files) для заданной комбинации.

    TODO(python-dev): актуальные URL-ы моделей GigaAM-v3 искать в:
      - sherpa-onnx docs: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/
      - HuggingFace: https://huggingface.co/sberbank-ai (или salute-developers/GigaAM)
      - k2-fsa release tags: https://github.com/k2-fsa/sherpa-onnx/releases
    Silero VAD:
      - https://github.com/k2-fsa/sherpa-onnx/releases (asset silero_vad.onnx)
    Hotwords:
      - файл создаётся локально в install_gigaam_bundle из TTRPG_HOTWORDS (ниже).
    Сохранить URL-ы, sha256, sizes прямо в коде этой функции
    (короткий mapping словарь); НЕ ходить в интернет за манифестом.
    """
    ...


# Минимальный стартовый набор hotwords для D&D/PF2e на русском.
# Расширяется пользователем через отдельный механизм в будущем (YAGNI сейчас).
TTRPG_HOTWORDS: tuple[str, ...] = (
    "д20", "д6", "д8", "д10", "д12", "д100",
    "криттен", "крит", "натурал",
    "пасфайндер", "паладин", "паладина",
    "варвар", "варлок", "бард", "клирик", "друид",
    # TODO(python-dev): расширить ~40-80 слов, взять из speaker_map.json
    # и общих D&D терминов; обсудить с ml-specialist.
)


def install_gigaam_bundle(params, progress: InstallProgress | None) -> None:
    """Идемпотентная установка GigaAM bundle.

    Flow:
      1) если уже установлено корректно — return (is_installed внешний guard,
         но здесь дополнительная страховка).
      2) качаем всё во временный каталог (atomic move в конце).
      3) проверяем sha256 каждого файла.
      4) генерируем hotwords.txt локально.
      5) атомарно перемещаем temp → финальный каталог.
      6) записываем version.json (последним — это маркер «всё ок»).
    """
    bundle_version, remote_files = _bundle_files(params)
    target_dir = gigaam_module_dir(params)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    total_bytes = sum(f.size for f in remote_files)
    downloaded_bytes = 0
    last_emit = 0.0
    emit_interval_sec = 0.25  # throttle

    def _notify(msg: str, extra_bytes: int = 0) -> None:
        nonlocal downloaded_bytes, last_emit
        downloaded_bytes += extra_bytes
        now = time.monotonic()
        if progress is None:
            return
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

        # Generate hotwords.txt
        (tmp_dir / "hotwords.txt").write_text(
            "\n".join(TTRPG_HOTWORDS) + "\n",
            encoding="utf-8",
        )

        # Собрать VersionInfo
        files_map = {rf.logical: rf.relpath for rf in remote_files}
        files_map["hotwords"] = "hotwords.txt"
        sizes_map = {rf.relpath: rf.size for rf in remote_files}
        sizes_map["hotwords.txt"] = (tmp_dir / "hotwords.txt").stat().st_size
        sha_map = {rf.relpath: rf.sha256 for rf in remote_files}
        sha_map["hotwords.txt"] = sha256_file(tmp_dir / "hotwords.txt")

        info = VersionInfo(
            schema_version=GIGAAM_SCHEMA_VERSION,
            bundle_version=bundle_version,
            variant=params.variant.value,
            precision=params.precision.value,
            files=files_map,
            file_sizes=sizes_map,
            file_sha256=sha_map,
        )

        # Атомарный swap: удалить старое, переместить tmp → target
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.move(str(tmp_dir), str(target_dir))

    # version.json пишем ПОСЛЕ перемещения — маркер «installation complete».
    # Если установка прервана между move и write — is_installed вернёт False
    # благодаря отсутствию version.json, и install() повторится.
    write_version_file(target_dir, info)
    if progress is not None:
        progress(1.0, "Установка GigaAM завершена")


def _download_with_progress(
    url: str,
    dst: Path,
    expected_size: int,
    notify,
    label: str,
) -> None:
    req = Request(url, headers={"User-Agent": "ttrpg-transcriber-installer"})
    with urlopen(req, timeout=60) as response, dst.open("wb") as out:
        chunk_size = 1 << 16
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            notify(f"Скачивание {label}...", extra_bytes=len(chunk))
```

---

### 4.3 `sources/speech/_gigaam_vad.py`

```python
"""Silero VAD wrapper — внутренняя деталь GigaAM модуля (ADR-013).

Не экспортируется; импортируется только из gigaam.py.
"""

from __future__ import annotations

from sources.speech._gigaam_paths import gigaam_module_dir, read_version_file


def build_vad(params, tuning, num_threads: int):
    """Построить sherpa_onnx.VoiceActivityDetector с Silero.

    Path берётся из version.json чтобы не дублировать имена файлов.
    """
    import sherpa_onnx

    module_dir = gigaam_module_dir(params)
    info = read_version_file(module_dir)
    assert info is not None, "build_vad called before install completed"

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(module_dir / info.files["vad"])
    config.silero_vad.threshold = tuning.threshold
    config.silero_vad.min_silence_duration = tuning.min_silence_duration
    config.silero_vad.min_speech_duration = tuning.min_speech_duration
    config.silero_vad.max_speech_duration = tuning.max_speech_duration
    config.silero_vad.window_size = tuning.window_size
    config.sample_rate = tuning.sample_rate
    config.num_threads = tuning.num_threads

    return sherpa_onnx.VoiceActivityDetector(
        config,
        buffer_size_in_seconds=100.0,
    )
```

---

## 5. `core/backend_installers.py` — shim для UI

**Зачем нужен:** dependency rules `§3 ARCHITECTURE.md` строго запрещают `ui → sources`. Installer UI и GUI не могут напрямую импортировать `GigaAMSource`. Нужен slim в `core/`, который:
- знает конкретный тип `GigaAMSource` и `GigaAMInstallParams`;
- выставляет UI-friendly API (имена backend-ов, человекочитаемые описания, суммарные размеры);
- пробрасывает `InstallProgress` с throttling.

```python
"""Core shim over Installable sources. UI зовёт этот модуль, а не sources/.

Даёт UI-слою (cli.py, gui.py, launcher/installer_ui.py) тонкую
backend-agnostic ручку для установки моделей, НЕ раскрывая конкретные типы
sources/ наружу UI.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Callable

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
    # Будущее: GIGAAM_E2E_RNNT_FP32 и т.д.


@dataclass(frozen=True)
class BackendInfo:
    """Метаданные для отображения в GUI / installer wizard."""
    id: BackendId
    title: str                # "GigaAM-v3 (русский)"
    description: str          # "~900 MB. RNNT без встроенной пунктуации..."
    approx_download_bytes: int  # для прогресс-бара, пока не начато
    default_selected: bool    # checkbox по умолчанию в wizard


# Hardcoded registry — в стиле SPEECH_SOURCES (ADR-11).
BACKENDS: dict[BackendId, BackendInfo] = {
    BackendId.GIGAAM_RNNT_FP32: BackendInfo(
        id=BackendId.GIGAAM_RNNT_FP32,
        title="GigaAM-v3 RNNT (русский)",
        description=(
            "Русскоязычный ASR для TTRPG. ~900 MB. Без встроенной "
            "пунктуации — терминология бросков и характеристик "
            "сохраняется как есть."
        ),
        approx_download_bytes=950_000_000,
        default_selected=True,
    ),
}


def list_backends() -> list[BackendInfo]:
    return list(BACKENDS.values())


def is_backend_installed(backend_id: BackendId) -> bool:
    source, params = _resolve(backend_id)
    return source.is_installed(params)


def installed_size_bytes(backend_id: BackendId) -> int:
    source, params = _resolve(backend_id)
    return source.installed_size_bytes(params)


def install_backend(
    backend_id: BackendId,
    progress: InstallProgress | None = None,
) -> None:
    """Блокирующая установка. Вызывается из worker-thread UI-клиентами.

    Сам метод НЕ поднимает поток. Клиент (gui/installer_ui) обязан
    завернуть вызов в threading.Thread или concurrent.futures.
    """
    source, params = _resolve(backend_id)
    source.install(params, progress=progress)


def _resolve(backend_id: BackendId) -> tuple[Installable, object]:
    if backend_id == BackendId.GIGAAM_RNNT_FP32:
        return (
            GigaAMSource(
                variant=GigaAMVariant.RNNT,
                precision=GigaAMPrecision.FP32,
            ),
            GigaAMInstallParams(
                variant=GigaAMVariant.RNNT,
                precision=GigaAMPrecision.FP32,
            ),
        )
    raise ValueError(f"unknown backend: {backend_id}")
```

### 5.1 Dependency compliance check

- `ui/gui.py` импортирует `core.backend_installers` — OK (`ui → core`).
- `launcher/installer_ui.py` импортирует `core.backend_installers` — OK. `launcher/` формально не один из 6 слоёв, но логически это UI-рантайм для установщика; то же правило.
- `core.backend_installers` импортирует `sources.speech.gigaam` — OK (`core → sources`).
- `core.backend_installers` НЕ импортирует tkinter — OK.
- `sources.speech.gigaam` импортирует только `domain.*` и `sources.base` + sibling `_gigaam_*` — OK.
- Никто из `mergers/renderers` не трогается — OK.

### 5.2 Progress throttling — thread-safety

`InstallProgress` callback вызывается из worker-thread. UI-клиент реализует callback так:

```python
# В installer_ui.py / gui.py worker
def _on_progress(fraction: float, message: str) -> None:
    # thread-safe enqueue
    self._progress_queue.put((fraction, message))

# В main-thread via root.after(100, ...)
def _poll_progress(self) -> None:
    while not self._progress_queue.empty():
        fraction, msg = self._progress_queue.get_nowait()
        self.progress_var.set(fraction * 100)
        self.status_label.config(text=msg)
    self.root.after(100, self._poll_progress)
```

Throttling уже сделан внутри `_gigaam_download._notify` (раз в 250 мс). Дополнительная защита на стороне UI не требуется. Message format — human-readable рус, например «Скачивание encoder.onnx...» или «Установка GigaAM завершена».

---

## 6. Runtime flow `GigaAMSource.extract()`

**Ключевые требования к формату аудио** (от ml-specialist, см. §6.5):
- sherpa-onnx `accept_waveform` ждёт `float32` нормализованный в `[-1.0, 1.0]`;
- Craig пишет 48 kHz `int16` PCM (FLAC/opus) — нужен resample 48→16 kHz + normalize;
- `soxr.resample(..., out_type="float32")` уже отдаёт нормализованный float32;
- `scipy.signal.resample_poly` отдаёт `float64` → явный `.astype(np.float32)` + `/ 32768.0` если source был int16.

```python
def _transcribe_track(self, audio_path: Path, speaker: str | None) -> list[SpeechSegment]:
    import numpy as np

    # 1. Загрузка + resample + нормализация
    samples_48k_int16, sr_native = _load_audio_int16_mono(audio_path)  # soundfile
    samples_16k_float32 = _resample_to_16k_float32(samples_48k_int16, sr_native)
    # samples_16k_float32: dtype=float32, values ∈ [-1.0, 1.0], sr=16000

    # 2. Silero VAD через sherpa-onnx streaming API
    vad = self._vad
    vad.reset()

    segments_out: list[SpeechSegment] = []
    window = 512  # silero work window (32 ms @ 16 kHz)
    i = 0
    n = len(samples_16k_float32)

    while i + window <= n:
        vad.accept_waveform(samples_16k_float32[i : i + window])
        while not vad.empty():
            speech = vad.front              # см. sherpa-onnx VAD API
            vad.pop()
            seg = self._recognize_segment(speech, speaker)
            if seg is not None:
                segments_out.append(seg)
        i += window

    # Финальный flush — отдаём остаток короче window
    vad.flush()
    while not vad.empty():
        speech = vad.front
        vad.pop()
        seg = self._recognize_segment(speech, speaker)
        if seg is not None:
            segments_out.append(seg)

    return segments_out


def _recognize_segment(self, speech, speaker: str | None) -> SpeechSegment | None:
    """Распознать один VAD-сегмент, применить фильтры мусорных сегментов.

    Фильтры (см. §6.5, защита от галлюцинаций):
      1. Пустой/слишком короткий текст (< 2 символов) → None.
      2. Пение/музыка: длинный сегмент с очень редким выводом
         (>2 сек + <0.5 симв/сек) → None.
    """
    stream = self._recognizer.create_stream()
    stream.accept_waveform(16000, speech.samples)
    self._recognizer.decode_stream(stream)
    text = stream.result.text.strip()

    # Фильтр 1: короткий мусор (артефакт VAD-cut или одиночный blank)
    if len(text) < 2:
        return None

    start_sec = speech.start / 16000.0
    duration_sec = len(speech.samples) / 16000.0
    end_sec = start_sec + duration_sec

    # Фильтр 2: длинный сегмент с редким выводом = вероятно не речь (пение/шум)
    if duration_sec > 2.0 and (len(text) / duration_sec) < 0.5:
        logger.debug(
            "GigaAM: dropping low-density segment (%.1fs, %d chars): %r",
            duration_sec, len(text), text[:40],
        )
        return None

    return SpeechSegment(
        start=start_sec,
        end=end_sec,
        speaker=speaker,
        text=text,
        confidence=None,  # sherpa-onnx RNNT не даёт прямого score; см. §6.5
    )
```

**TODO(python-dev):** точный API `VoiceActivityDetector.front/pop/flush` — свериться со свежей sherpa-onnx Python docs (1.12+). Выше — псевдокод по контракту ml-specialist. Если в реальном API `flush()` называется иначе или передаёт финальный chunk через `accept_waveform(is_final=True)` — адаптировать.

**Почему `confidence=None`:** согласно ADR-8 canonical JSON пишет только required поля. `ys_log_probs` (per-token log-probabilities) доступны в `OfflineRecognitionResult` начиная с PR #3077, но консольный потребитель confidence появится только на этапе работы с эмоциями. До того — оставляем None.

**Память на длинных треках.** sherpa-onnx OfflineRecognizer обрабатывает сегменты stateless: каждый `create_stream()` создаёт новый объект, после извлечения `result.text` объект отбрасывается. Утечки на 6-часовом треке быть не должно — проверить на smoke-тесте.

---

## 6.5 Runtime params — обоснование и источники (от ml-specialist)

Все параметры `OfflineRecognizer` и конкретные инженерные решения в §3 и §6
основаны на ресёрче ml-specialist'а по актуальной документации sherpa-onnx
1.12+ и GigaAM-v3 ONNX экспорту. Секция существует, чтобы python-dev при
сомнениях мог посмотреть ОБОСНОВАНИЕ без перехода в сторонние доки.

### 6.5.1 `model_type="nemo_transducer"` (не `"transducer"`)

GigaAM-v3 основан на NVIDIA NeMo Conformer-RNNT. В sherpa-onnx
`model_type="transducer"` — это k2/Icefall-based (другой формат encoder/
decoder signatures). `"nemo_transducer"` — именно для NeMo-exported ONNX.

Использование неверного `model_type` → либо load error при инициализации,
либо модель загружается но декодирование возвращает мусор.

**Источник:** [NeMo transducer-based models — sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html)

### 6.5.2 `modeling_unit="cjkchar"` (не BPE) — критическая проверка

GigaAM-v3 использует **char-level** токенайзер (~34 токена): `▁` (пробел) +
32 кириллические буквы (`а`–`я`) + `<blk>`. Это подтверждено кодом экспорта
в репозитории `istupakov/gigaam-v3-onnx`:

```python
# export script
for i, token in enumerate(["▁", *(chr(ord("а") + i) for i in range(32)), "<blk>"]):
    ...
```

Для char-level моделей `modeling_unit="cjkchar"` — правильный режим
матчинга hotwords на уровне символов. BPE-specific параметры
(`modeling_unit="bpe"`, `bpe_vocab=...`) для GigaAM НЕ нужны и могут
сломать hotwords ContextGraph.

**⚠️ ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА ПЕРЕД ПЕРВЫМ ЗАПУСКОМ:** python-dev открывает
скачанный `tokens.txt` и смотрит формат строк:
- Строки вида `а 1`, `б 2`, `в 3`, ... — **char-level**, наш случай, код
  выше корректен.
- Строки вида `▁привет 1234`, `ть 567` — BPE субслова, тогда GigaAM уехал
  на BPE-токенайзер, и нужно `modeling_unit="bpe"` + `bpe_vocab=...`.
  (Для v3 не ожидается, но зафиксировать в checklist.)

**Источники:**
- [istupakov/gigaam-v3-onnx — HuggingFace](https://huggingface.co/istupakov/gigaam-v3-onnx)
- [Hotwords docs — sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html)

### 6.5.3 `feature_dim=80`, `sample_rate=16000`

NeMo/GigaAM использует 80-мерные mel-filterbank features — стандарт NeMo
`AudioToMelSpectrogramPreprocessor`. Для `from_transducer()` параметры
`feature_dim` и `sample_rate` передаются напрямую, отдельный
`OfflineFeatureExtractorConfig` объект не нужен.

Неправильный `feature_dim` → shape mismatch exception при первом inference.

**Источник:** [NeMo transducer models page — sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html)

### 6.5.4 Conditional `decoding_method` + PR #3077 риск

**Hotwords биасинг работает ТОЛЬКО с `modified_beam_search`.** ContextGraph
sherpa-onnx требует ветвления путей — одиночный path greedy не даёт механизма
применения бонуса.

**PR #3077** («Add modified beam search and hotwords support for NeMo
transducer models», смержен февраль 2026, доступно в sherpa-onnx 1.12+)
добавил beam search и hotwords для NeMo-ветки. До 1.12 на NeMo моделях
`hotwords_file=...` тихо игнорировался.

**Известный риск (issue #3267):** ~20% случаев галлюцинаций или пустого
вывода на **NeMo TDT** моделях (Token-and-Duration Transducer) при
`modified_beam_search` vs `greedy_search` на том же сегменте. GigaAM-v3 —
**классический RNNT, не TDT**, духовность проблемы для RNNT ниже, но
общая часть beam-expansion кода разделена, поэтому нельзя исключить
случайные регрессии.

**Стратегия проекта:** `_pick_decoding_method()` (§3) возвращает
`greedy_search` если hotwords-файл пустой или отсутствует, иначе
`modified_beam_search`. Цена beam search платится только пользователями,
которые осознанно настраивали hotwords. Дефолтная установка → greedy,
быстрее и без риска.

**Дополнительная страховка** — фильтры мусорных сегментов в
`_recognize_segment()` (§6): ловят edge-case галлюцинаций независимо от
decoding method.

**Минимальная версия `sherpa-onnx` в `pyproject.toml`:**
```toml
sherpa-onnx = ">=1.12.0,<2.0"
```
Нижняя граница — из-за PR #3077. Верхняя — страховка от major breaking.

**Источники:**
- [PR #3077 — sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/pull/3077)
- [Issue #3267 — hallucinations on NeMo TDT](https://github.com/k2-fsa/sherpa-onnx/issues/3267)
- [Hotwords docs](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html)

### 6.5.5 `hotwords_score=1.5`

Официальный default sherpa-onnx. `1.5` — умеренный boost, работает на
TTRPG-именах средней длины (2–3 слога). Для коротких сложных терминов
(«Тал-Нир», «Маэри») можно поднять до `2.0`; для очень уникальных
(«Ачакек») — до `3.0`. Диапазон выше `3.5` ломает обычную речь.

Per-hotword override доступен синтаксисом `слово :score` в `hotwords.txt`
(score строго в конце строки после пробела).

**Источник:** [Hotwords docs](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html)

### 6.5.6 `num_threads=4`

Оптимум CPU-bound ONNX inference на типовом 8-ядерном десктопе. Бенчмарки
на Cortex A76: 1→2 потока = +70%, 2→4 = +60%, 4→8 = −50% (cache contention).
На x86 паттерн аналогичный. GigaAM-v3 Conformer (220M params fp32) —
memory-bound, больше 4 не имеет смысла.

Пользователь может переопределить через `PipelineParams.num_threads`, но
default `4` — safe.

**Источник:** [Performance optimization — sherpa DeepWiki](https://deepwiki.com/k2-fsa/sherpa/7.3-performance-optimization)

### 6.5.7 CUDA detection через `onnxruntime.get_available_providers`

`sherpa-onnx` CUDA — отдельный wheel (`sherpa-onnx==X.Y+cuda`, index
`https://k2-fsa.github.io/sherpa/onnx/cuda.html`). Стандартный
`pip install sherpa-onnx` → CPU-only. Передача `provider="cuda"` в CPU-only
сборке → runtime error.

`onnxruntime` — dependency sherpa-onnx, всегда установлен. Проверка:

```python
import onnxruntime as ort
cuda_available = "CUDAExecutionProvider" in ort.get_available_providers()
```

Если пользователь в GUI/CLI выбрал `device=cuda`, а CUDA недоступна →
warning в лог + fallback на CPU. Не падаем. См. `_detect_provider()` в §3.

**Windows-специфика:** DirectML как альтернатива CUDA на Windows в
sherpa-onnx публично не задокументирована — не использовать без
предварительного тестирования.

**Источники:**
- [GPU Support — sherpa-onnx DeepWiki](https://deepwiki.com/k2-fsa/sherpa-onnx/7.1-gpu-support-(cuda-and-directml))
- [CUDA Execution Provider — onnxruntime docs](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)

### 6.5.8 Warmup dummy-inference

Загрузка ONNX в память (~900 MB fp32) + ONNX Runtime JIT compilation графа
на первом прогоне = 5–9 сек задержки до первого результата. Критично для
UX: пользователь нажал «Start» и видит зависание без обратной связи.

Решение: в `_ensure_loaded()` после создания recognizer прогоняем
**один dummy inference** на 0.5 сек float32 zeros. Это триггерит JIT,
и дальше первый реальный сегмент обрабатывается без дополнительной
задержки.

0.5 сек выбрано потому что короче 0.25 сек некоторые компиляторы не
активируют оптимизированные kernels, а длиннее бессмысленно.

### 6.5.9 Фильтры мусорных сегментов

**Фильтр 1: `len(text) < 2`.** Ловит пустые строки и одиночные символы,
которые возникают от VAD-cuts на переходных шумах (щелчки микрофона,
дыхание). Дёшев, безопасен.

**Фильтр 2: density < 0.5 символов/сек на сегментах > 2 сек.** Ловит
пение/музыку, которую silero VAD пропустил как речь. Типичный музыкальный
сегмент бард-кастинга RNNT выдаст как 3–5 искажённых слогов на 10 секунд
— это заметно ниже 0.5 симв/сек. Порог `0.5` подобран с запасом (нормальная
русская речь ≥ 5–8 симв/сек).

**Ошибочно НЕ отфильтруется:** очень короткие междометия («ага», «да»)
в коротких сегментах — но они и не попадают под фильтр 2 (duration ≤ 2 сек).

**Ошибочно отфильтруется:** длинная пауза с одним-двумя словами в конце
(«хмм... понял») где VAD не разбил на два сегмента. Edge case, редко.
Можно пересмотреть если появятся жалобы.

**Галлюцинации на тишине:** RNNT архитектурно эмитит blank на silent
фреймах, не вынужден «завершать» последовательность как Whisper
encoder-decoder. GigaAM существенно менее склонен к whisper-style
повторяющимся галлюцинациям. Фильтр 1 покрывает остаток.

### 6.5.10 TTRPG-лексика и ITN

Base RNNT (variant `rnnt`, не `e2e_rnnt`) **не имеет встроенной ITN**
(Inverse Text Normalization) — не конвертирует числа в цифры, не ставит
пунктуацию. Для TTRPG это хорошо: нотация кубиков «1d20» в речи не
произносится как «один-дэ-двадцать», а как «двадцатка», «натуральная
двадцатка», «к двадцати» — и именно так RNNT их передаст.

**Hotwords биасим на реальные произнесённые фразы**, не на нотацию:
```
двадцатка
натуральная
спасбросок
испытание
инициатива
концентрация
```

Если нужна именно нотация `1d20` в финальном тексте — это **post-processing
regex на уровне `mergers/` или `renderers/`**, не ASR. В этом спеке не
делаем.

**Variant `e2e_rnnt`** включает встроенную ITN и пунктуацию — опция для
пользователей, кому нужен готовый к чтению текст без post-processing.
Параметризуемо через `GigaAMVariant` enum, но **default — `rnnt`**.

---

## 7. Интеграция с `installer_ui.py` — чекбокс

### Правки в `launcher/installer_ui.py`

1. **Добавить стадию «models»** в `STEPS`:
   ```python
   STEPS = [
       ("python",   "..."),
       ("pip",      "..."),
       ("pytorch",  "..."),
       ("whisperx", "..."),  # TODO(python-dev): уточнить, остаётся ли
       ("ffmpeg",   "..."),
       ("models",   "Загрузка моделей"),  # NEW
   ]
   STEP_WEIGHTS = {..., "models": 15}  # уменьшить другие пропорционально
   ```

2. **Checkbox UI перед стартом.** В `_build_ui()` добавить секцию «Дополнительные модели» с чекбоксом для каждого `BackendInfo` из `core.backend_installers.list_backends()`. Default-checked при `info.default_selected`.

   ```python
   # В installer_ui.py
   from core.backend_installers import BackendId, install_backend, list_backends

   self._backend_checkboxes: dict[BackendId, tk.BooleanVar] = {}
   for info in list_backends():
       var = tk.BooleanVar(value=info.default_selected)
       self._backend_checkboxes[info.id] = var
       cb = tk.Checkbutton(
           backends_frame,
           text=f"{info.title} ({info.approx_download_bytes // 1_000_000} MB)",
           variable=var, bg=BG, fg=FG, selectcolor=BG2,
           activebackground=BG, activeforeground=FG,
       )
       cb.pack(anchor="w")
       # описание под чекбоксом мелким шрифтом:
       tk.Label(backends_frame, text=info.description,
                font=("Segoe UI", 8), fg=FG_DIM, bg=BG,
                wraplength=560, justify="left").pack(anchor="w", padx=(20, 0))
   ```

3. **В worker** после `ffmpeg` шага:
   ```python
   self._begin_step("models")
   selected = [
       bid for bid, var in self._backend_checkboxes.items() if var.get()
   ]
   for idx, backend_id in enumerate(selected):
       self._log(f"Установка {backend_id.value}...")
       def _prog(frac: float, msg: str, _idx=idx, _total=len(selected)) -> None:
           # локальная фракция одного backend → общий прогресс стадии
           stage_frac = (_idx + frac) / _total * 100
           self._step_progress_fn("models")(stage_frac)
           self._log(msg)
       install_backend(backend_id, progress=_prog)
   self._complete_step("models")
   ```

   Важно: `install_backend` вызывается **внутри** `_install_worker()`, который уже крутится в daemon thread. Повторный `threading.Thread` не нужен. Прогресс-callback уже thread-safe благодаря `_log_queue` и `root.after`.

---

## 8. Интеграция с `ui/gui.py` — lazy modal

Перед запуском пайплайна (обработчик кнопки «Run»):

```python
# ui/gui.py (псевдокод)
from core.backend_installers import (
    BackendId, install_backend, is_backend_installed,
)

def _on_run_clicked(self) -> None:
    if self.selected_backend == "gigaam":
        if not is_backend_installed(BackendId.GIGAAM_RNNT_FP32):
            if not self._show_install_modal(BackendId.GIGAAM_RNNT_FP32):
                return  # пользователь отменил
    self._start_pipeline_worker()


def _show_install_modal(self, backend_id: BackendId) -> bool:
    """Показать модальное окно установки. Вернуть True если установка успешна."""
    modal = tk.Toplevel(self.root)
    modal.title("Установка модели")
    modal.geometry("480x220")
    modal.transient(self.root)
    modal.grab_set()
    # ... progress bar, status label, cancel button
    result = {"ok": False}
    progress_q: queue.Queue = queue.Queue()

    def _worker():
        try:
            install_backend(
                backend_id,
                progress=lambda f, m: progress_q.put((f, m)),
            )
            result["ok"] = True
        except Exception as e:
            progress_q.put((-1.0, f"Ошибка: {e}"))
        finally:
            progress_q.put(None)  # sentinel

    threading.Thread(target=_worker, daemon=True).start()

    # poll loop на main thread
    def _poll():
        try:
            while True:
                item = progress_q.get_nowait()
                if item is None:
                    modal.destroy()
                    return
                fraction, msg = item
                if fraction >= 0:
                    pb["value"] = fraction * 100
                status_lbl.config(text=msg)
        except queue.Empty:
            pass
        modal.after(100, _poll)
    modal.after(100, _poll)
    self.root.wait_window(modal)
    return result["ok"]
```

**Почему модалка а не full window:** установка в этом контексте — вторичная операция (пользователь уже в основном окне, запускает пайплайн). Модалка блокирует только обработку пайплайна, не весь GUI в смысле переразметки. Первичный установщик — `launcher/installer_ui.py`, уже полный экран.

---

## 9. Правки `core/pipeline.py`

```python
# _speech_kwargs: добавить ветку
def _speech_kwargs(params: PipelineParams, cls: type[Source]) -> dict:
    if cls.__name__ == "FasterWhisperSource":
        return {...}
    if cls.__name__ == "WhisperXSource":
        return {...}
    if cls.__name__ == "GigaAMSource":
        return {
            "variant": params.gigaam_variant,
            "precision": params.gigaam_precision,
            "device": params.device,
            "num_threads": params.num_threads,
            "speaker_map": params.speaker_map,
        }
    raise ValueError(...)
```

Добавить в `PipelineParams`:

```python
@dataclass(frozen=True)
class PipelineParams:
    speech_backend: str = "faster-whisper"
    ...
    # GigaAM-only (игнорируются другими backend-ами)
    gigaam_variant: str = "rnnt"       # "rnnt" | "e2e_rnnt"
    gigaam_precision: str = "fp32"     # "fp32" | "int8"
    num_threads: int = 4
```

И в `sources/__init__.py`:

```python
from sources.speech.gigaam import GigaAMSource

SPEECH_SOURCES: dict[str, type[Source]] = {
    "faster-whisper": FasterWhisperSource,
    "whisperx": WhisperXSource,
    "gigaam": GigaAMSource,
}
```

---

## 10. Правки `ui/cli.py`

```python
ap.add_argument(
    "--speech_backend",
    default="faster-whisper",
    choices=sorted(SPEECH_SOURCES.keys()),  # теперь включает "gigaam"
)
ap.add_argument("--gigaam_variant", default="rnnt", choices=["rnnt", "e2e_rnnt"])
ap.add_argument("--gigaam_precision", default="fp32", choices=["fp32", "int8"])
ap.add_argument("--num_threads", type=int, default=4)
```

CLI **не** вызывает установку сам. Если пользователь запустил CLI с `--speech_backend gigaam` и модель не установлена — `GigaAMSource._ensure_loaded()` поднимет `RuntimeError` с сообщением «Run installer or GigaAMSource().install(...)». Это намеренно: desktop-app paradigm (п.6 constraints) говорит что установка — GUI-операция. CLI — для пользователей которые уже прошли через installer.

---

## 11. `scripts/download_gigaam.py` — dev/CI обёртка

```python
"""Dev/CI utility — install GigaAM bundle without GUI.

Это НЕ user-facing скрипт. User ставит модели через installer_ui.py или
in-app modal. Этот скрипт для разработчиков, CI smoke-тестов и
troubleshooting.
"""

from __future__ import annotations

import argparse
import sys

from core.backend_installers import BackendId, install_backend


def main() -> int:
    ap = argparse.ArgumentParser(prog="download_gigaam")
    ap.add_argument(
        "--backend",
        default=BackendId.GIGAAM_RNNT_FP32.value,
        choices=[b.value for b in BackendId],
    )
    args = ap.parse_args()

    def _prog(fraction: float, msg: str) -> None:
        sys.stdout.write(f"\r[{int(fraction*100):3d}%] {msg:<60}")
        sys.stdout.flush()

    install_backend(BackendId(args.backend), progress=_prog)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Тонкий** — ровно 20 строк. Никакой своей логики, только обёртка над core-шимом.

---

## 12. Тесты (для `qa-engineer`)

### 12.1 Unit тесты (быстрые, без сети)

Файл: `tests/sources/speech/test_gigaam_paths.py`

- `test_version_file_roundtrip` — write → read → equal.
- `test_read_version_missing_returns_none`.
- `test_read_version_corrupt_json_returns_none`.
- `test_gigaam_module_dir_respects_models_root` — передаёт tmp_path, получает `tmp_path/gigaam/rnnt-fp32`.

Файл: `tests/sources/speech/test_gigaam_is_installed.py`

- `test_is_installed_empty_dir_false`.
- `test_is_installed_valid_true` — создать fake version.json + fake файлы правильных размеров.
- `test_is_installed_schema_mismatch_false` — version.json с schema_version=999.
- `test_is_installed_variant_mismatch_false`.
- `test_is_installed_file_size_mismatch_false`.

Файл: `tests/sources/speech/test_gigaam_install.py`

- `test_install_downloads_and_writes_version` — monkeypatch `urlopen` и `_bundle_files` на маленькие фейки, проверить что в target_dir есть все файлы + version.json.
- `test_install_sha_mismatch_raises` — fake файл с неправильным hash.
- `test_install_on_corrupt_existing_reinstalls` — положить кривой version.json, запустить install, получить чистую установку.
- `test_install_progress_called` — счётчик вызовов > 0, финальный `fraction >= 0.99`.
- `test_install_temp_cleanup_on_failure` — симулировать исключение после download, проверить что `target_dir.parent/gigaam-install-*` пуст.

Файл: `tests/sources/speech/test_gigaam_vad.py`

- `test_vad_segments_three_pulses` — синтетическое 10-секундное аудио: silence + 3 импульса (sine bursts) + silence. Проверить что VAD вернул 3 сегмента с правильными приблизительными start. **Требует реальный `silero_vad.onnx`** — маркер `@pytest.mark.requires_gigaam_vad`, пропускается если файла нет (чтобы CI без моделей не падал).

Файл: `tests/core/test_backend_installers.py`

- `test_list_backends_returns_gigaam`.
- `test_install_backend_dispatches_to_gigaam_install` — monkeypatch `GigaAMSource.install`, проверить что вызвался с правильными params.

Файл: `tests/sources/speech/test_gigaam_runtime.py` — **runtime-параметры и фильтры (§6.5)**

- `test_pick_decoding_method_no_file_returns_greedy` — `hotwords_file=None` → `"greedy_search"`.
- `test_pick_decoding_method_missing_file_returns_greedy` — передать путь к несуществующему файлу.
- `test_pick_decoding_method_empty_file_returns_greedy` — пустой файл → `"greedy_search"`.
- `test_pick_decoding_method_whitespace_only_returns_greedy` — файл с только `\n\n  \n`.
- `test_pick_decoding_method_with_hotwords_returns_beam_search` — файл с `азлант\n` → `"modified_beam_search"`.
- `test_detect_provider_cpu_default` — `device="cpu"` → `"cpu"` без обращения к onnxruntime.
- `test_detect_provider_cuda_unavailable_falls_back_cpu` — monkeypatch `ort.get_available_providers` → возвращает только `["CPUExecutionProvider"]` → `"cpu"` + warning в лог.
- `test_detect_provider_cuda_available_returns_cuda` — mock возвращает `["CUDAExecutionProvider", "CPUExecutionProvider"]` → `"cuda"`.
- `test_recognize_segment_empty_text_returns_none` — fake recognizer возвращает `""` → `None`.
- `test_recognize_segment_one_char_returns_none` — fake recognizer возвращает `"а"` → `None` (фильтр `< 2`).
- `test_recognize_segment_low_density_long_segment_returns_none` — duration=5s, text="ла ла", len/dur ≈ 0.2 → `None`.
- `test_recognize_segment_normal_speech_returns_segment` — duration=3s, text="двадцать урона", len/dur ≈ 5 → `SpeechSegment` с правильным start/end.
- `test_recognize_segment_short_low_density_passes` — duration=1.5s (< 2), text="да" (len=2) → проходит фильтр 2 (гейт на duration > 2).
- `test_warmup_recognizer_calls_decode_once` — mock recognizer, после `_warmup_recognizer(mock)` проверить `mock.decode_stream.call_count == 1` и что передавалось float32 zeros.
- `test_build_recognizer_passes_nemo_transducer_and_cjkchar` — monkeypatch `sherpa_onnx.OfflineRecognizer.from_transducer`, capture kwargs, assert `model_type == "nemo_transducer"`, `modeling_unit == "cjkchar"`, `feature_dim == 80`, `sample_rate == 16000`.
- `test_build_recognizer_hotwords_only_when_beam_search` — с пустым hotwords.txt → в kwargs НЕТ `hotwords_file`/`hotwords_score`; с непустым → они есть и `decoding_method=modified_beam_search`.

### 12.2 Integration (медленные, маркер `@pytest.mark.slow`, выключены в default CI)

Файл: `tests/integration/test_gigaam_end_to_end.py`

- `test_real_install_to_tmp_dir` — настоящая установка в tmp, проверка `is_installed == True`, cleanup.
- `test_extract_on_fixture_audio` — работает только после установки, использует фиксированный wav с одним спикером, проверяет что вернулся минимум 1 `SpeechSegment` и text не пустой.

Конфигурация маркера в `pytest.ini`/`pyproject.toml`:

```ini
[tool.pytest.ini_options]
markers = [
  "slow: tests that download models or run full ASR (disabled by default)",
  "requires_gigaam_vad: tests needing installed silero_vad.onnx",
]
addopts = "-m 'not slow'"
```

---

## 13. ADR-013 — GigaAM как независимый модуль

Файл: `docs/adr/ADR-013-gigaam-independent-module.md`

```markdown
# ADR-013: GigaAM speech backend — независимый модуль с собственным VAD

## Decision

`GigaAMSource` реализуется как полностью самодостаточный модуль в
`sources/speech/gigaam.py`. Все runtime-зависимости модуля (GigaAM encoder/
decoder/joiner, tokens, Silero VAD, hotwords) живут в одном каталоге
`<models_root>/gigaam/<variant>-<precision>/` и управляются самим модулем
через `Installable` Protocol. Shared инфраструктуры для VAD или download
между source-ами НЕ создаётся.

## Context

При проектировании GigaAM backend-а рассмотрены три варианта размещения
Silero VAD:

1. **Shared `sources/_infra/vad/silero.py`** — общий VAD для всех будущих
   ASR backend-ов.
2. **Core service `core/vad_service.py`** — централизованный VAD по
   запросу, один файл `silero_vad.onnx` на проект.
3. **Внутренняя деталь модуля** — silero_vad.onnx живёт в каталоге
   GigaAM, импортируется только из `gigaam.py`.

## Выбрано — вариант 3. Обоснование.

- **Один потребитель.** faster-whisper получает VAD от ctranslate2 через
  `vad_filter=True`; WhisperX — свой pyannote-based VAD. На момент P2
  единственный клиент Silero — GigaAM. Shared инфраструктура для одного
  клиента — преждевременное обобщение (YAGNI, §principle из
  ARCHITECTURE.md).
- **Независимость модуля upgrade-а.** GigaAM bundle может включать
  specific-версию Silero ONNX (совместимость с тренированным VAD threshold
  tuning). Shared Silero значит что апгрейд GigaAM может сломать
  faster-whisper или будущие модули.
- **Размер overhead тривиален.** silero_vad.onnx ~2 MB. Если завтра
  появится второй потребитель — он получит свою копию. 4 MB на диске
  дешевле чем shared-инфраструктурный слой.
- **Установка как единый atomic action.** `GigaAMSource.install()` знает
  что выкачать именно эти файлы вместе, в одну директорию, одной версией.
  Распределённое владение ("VAD качается core-сервисом, модель — source-ом")
  усложняет реиндрамы и rollback.

## Consequences

- (+) Каждый speech backend полностью автономен. Добавление/удаление
  backend не трогает соседей.
- (+) `sources/_infra/` или `sources/_shared/` не создаётся (нет
  преждевременной абстракции).
- (+) `Installable` Protocol (§sources/base.py) — единственный общий
  контракт, и он тоже тривиален (три метода).
- (+) Тестирование проще: fake_models_root per test, без координации с
  другими backend-ами.
- (−) Если в P6+ появится второй потребитель Silero (например
  `sources/emotion/ru_speech_emotion.py`), будет две копии onnx файла
  (4 MB вместо 2). Acceptable.
- (−) Если GigaAM и будущий backend захотят разные версии Silero —
  проблема решается автоматически (каждый качает свою). Если одну —
  дублирование. Пересмотрим только когда будет конкретный 2-й потребитель.

## Trigger для пересмотра

- Появился 2-й or 3-й Installable source который использует Silero, И
- Все они согласны на одну и ту же версию Silero, И
- Размер модели > 20 MB (тогда 3x копии = 60 MB, что уже заметно).

Только при всех трёх условиях одновременно — вводим `sources/_infra/vad/`.
```

---

## 14. Layer rules compliance — итоговая проверка

| Импорт | Разрешён? |
|---|---|
| `sources/speech/gigaam.py` → `domain.annotations`, `domain.speaker_map`, `sources.base`, `sources.speech._gigaam_*` | ✓ (sources → domain + intra-layer siblings) |
| `sources/speech/_gigaam_*.py` → `sources.base`, `sources.speech._gigaam_paths` | ✓ |
| `core/backend_installers.py` → `sources.base`, `sources.speech.gigaam` | ✓ (core → sources) |
| `core/pipeline.py` → (расширение `_speech_kwargs`) | ✓ (core → sources, уже было) |
| `launcher/installer_ui.py` → `core.backend_installers` | ✓ (UI-layer → core) |
| `ui/gui.py` → `core.backend_installers` | ✓ (ui → core) |
| `ui/cli.py` → `core.PipelineParams` | ✓ (без новых импортов из sources) |
| `scripts/download_gigaam.py` → `core.backend_installers` | ✓ (скрипт — тонкая обёртка над core) |

**Запрещённые импорты отсутствуют.** В частности:
- `launcher/installer_ui.py` НЕ импортирует `sources.speech.gigaam` напрямую.
- `ui/gui.py` НЕ импортирует `sources.speech.gigaam` напрямую.
- `sources/speech/gigaam.py` НЕ импортирует ничего из `core/`, `ui/`, `mergers/`, `renderers/`.
- `_gigaam_*.py` НЕ импортируются из `sources/__init__.py` — невидимы снаружи модуля.

---

## 15. Follow-up задачи

### Для `python-dev`

1. **Найти URL и SHA256** актуальных GigaAM-v3 RNNT (fp32) файлов.
   - Точки поиска: sherpa-onnx pretrained models page, HuggingFace `salute-developers`/`sberbank-ai`, конкретно `istupakov/gigaam-v3-onnx` и `Smirnov75/GigaAM-v3-sherpa-onnx`, release assets `k2-fsa/sherpa-onnx`.
   - Заполнить `_bundle_files()` в `_gigaam_download.py`. Хардкодить прямо в коде; никаких remote manifest-ов.
   - Аналогично для `silero_vad.onnx` (из sherpa-onnx release).
2. Реализовать `_gigaam_paths.py`, `_gigaam_download.py`, `_gigaam_vad.py`, `gigaam.py` по контрактам выше.
3. Верифицировать точный API `sherpa_onnx.VoiceActivityDetector` в текущей версии пакета — уточнить цикл `accept_waveform/front/pop/flush` в `_transcribe_track`.
4. **⚠️ ОБЯЗАТЕЛЬНО ПЕРЕД ПЕРВЫМ ЗАПУСКОМ:** открыть скачанный `tokens.txt` и проверить, что он **char-level** (строки формата `а 1`, `б 2`, ...). Если вдруг BPE (`▁привет 1234`) — поменять `modeling_unit="cjkchar"` на `"bpe"` в `_build_recognizer()` + подключить `bpe_vocab=...`. См. §6.5.2.
5. Расширить `TTRPG_HOTWORDS` до ~40-80 слов — запросить у `ml-specialist` начальный набор для D&D/PF2e на русском.
6. **Зафиксировать минимальную версию `sherpa-onnx` >= 1.12.0** в `pyproject.toml`/`requirements.txt`. До 1.12 hotwords для NeMo моделей тихо игнорируются. См. §6.5.4.
7. Добавить `sherpa-onnx` (CPU) и опционально `sherpa-onnx-gpu` в `launcher/install_logic.py` как pip-пакеты на стадии `whisperx` → переименовать стадию в `asr_backends` или добавить отдельную.
8. Обновить `sources/__init__.py`, `core/pipeline.py`, `ui/cli.py`, `launcher/installer_ui.py`, `ui/gui.py` по §5, §9, §10.
9. Создать `scripts/download_gigaam.py` по §11.
10. Перед PR: пройти полный `ruff check` + `mypy` на новых модулях.

### Для `qa-engineer`

1. Реализовать все unit-тесты §12.1 (7 файлов).
2. Настроить маркеры `slow` и `requires_gigaam_vad` в `pyproject.toml`.
3. Реализовать `tests/integration/test_gigaam_end_to_end.py` с маркером `slow`.
4. Добавить fixture для синтетического аудио (silence + 3 sine bursts) — можно переиспользовать для других VAD-тестов.
5. Проверить что `pytest` без `-m slow` не скачивает ничего и не требует моделей.

### Для архитектора (меня)

1. После первой имплементации — ревью `_bundle_files()` на предмет что URL-ы идут с доверенного источника (HuggingFace/k2-fsa) и sha256 зафиксированы.
2. Проверить что никто не добавил shared infrastructure под шумок.
3. Следить за размером `launcher/installer_ui.py` — если checkbox-секция начинает разрастаться, выделить в отдельный widget.

### Для пользователя (перед мержем)

1. Принять решение по precision default: fp32 (~900 MB) vs int8 (~250 MB) как default для первого релиза. Текущая рекомендация в спеке — fp32, но это параметризуемо.
2. Проверить место на диске в `%APPDATA%/ttrpg-transcriber/models/` до запуска installer-а в рамках smoke-теста.
3. Одобрить стартовый список TTRPG_HOTWORDS (python-dev пришлёт после шага 4).

---

## 16. Что в спек НЕ вошло (намеренно)

- Settings → Models панель (YAGNI, п.9 constraints). `installed_size_bytes` оставлен в контракте для будущей бесплатной реализации.
- Emotion backend и его интеграция — не часть этого приоритета.
- Миграция faster-whisper на тот же `Installable` Protocol — `faster-whisper` не требует установки (скачивает через HuggingFace cache автоматически на первом запуске). Добавим если понадобится.
- Upgrade path между версиями GigaAM bundle — решается через bump `bundle_version` + переинсталл. Никакого отдельного `upgrade()` метода.
- Cancel installation — тривиально через флаг `threading.Event`, но не включено в Protocol (YAGNI: первая итерация — let it finish or crash-retry).

---

## Файлы для справки

Абсолютные пути, по которым принимались решения:

- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\ARCHITECTURE.md` — главный источник правил слоёв
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\base.py` — текущий `Source` ABC
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\speech\faster_whisper.py` — эталонный speech source
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\__init__.py` — registry
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\core\pipeline.py` — `PipelineParams` и `_speech_kwargs`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\launcher\installer_ui.py` — текущий wizard (STEPS, worker)
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\ui\gui.py` — GUI entry point
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\ui\cli.py` — CLI entry point

Файлы, которые будут созданы (абсолютные пути):

- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\speech\gigaam.py`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\speech\_gigaam_paths.py`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\speech\_gigaam_download.py`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\speech\_gigaam_vad.py`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\core\backend_installers.py`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\scripts\download_gigaam.py`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\docs\adr\ADR-013-gigaam-independent-module.md`

Файлы, которые будут модифицированы:

- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\base.py` — + `Installable`, `InstallProgress`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\sources\__init__.py` — + `GigaAMSource`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\core\pipeline.py` — + ветка `_speech_kwargs`, + поля `PipelineParams`
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\ui\cli.py` — + argparse опции
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\ui\gui.py` — + lazy install modal
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\launcher\installer_ui.py` — + checkbox + stage "models"
- `C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио\launcher\install_logic.py` — + sherpa-onnx pip package