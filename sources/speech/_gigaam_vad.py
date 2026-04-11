"""Silero VAD wrapper — внутренняя деталь GigaAM модуля (ADR-013).

Не экспортируется; импортируется только из ``sources/speech/gigaam.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sources.speech._bundle_download import files_by_logical, read_version_file
from sources.speech._gigaam_paths import gigaam_module_dir

if TYPE_CHECKING:
    from sources.speech.gigaam import GigaAMInstallParams, _VadTuning


def build_vad(
    params: "GigaAMInstallParams",
    tuning: "_VadTuning",
    num_threads: int,
) -> Any:
    """Построить ``sherpa_onnx.VoiceActivityDetector`` с Silero.

    Путь к silero_vad.onnx берётся из ``version.json`` чтобы не дублировать
    имена файлов с ``_gigaam_download``.

    Параметр ``num_threads`` сейчас не используется (VAD tuning хранит
    собственные num_threads для VAD модели), принимается для API-симметрии
    с ``_build_recognizer`` — на случай если в будущем захочется
    переиспользовать thread pool.
    """
    # Lazy import: sherpa_onnx — тяжёлая нативная зависимость. Держим
    # импорт внутри функции, чтобы unit-тесты без sherpa_onnx не падали.
    import sherpa_onnx

    del num_threads  # reserved for future use; tuning.num_threads is canonical

    module_dir = gigaam_module_dir(params)
    payload = read_version_file(module_dir)
    if payload is None:
        raise RuntimeError(
            "build_vad called before GigaAM install completed: "
            f"no version.json in {module_dir}"
        )
    files = files_by_logical(payload)

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(module_dir / files["vad"])
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
