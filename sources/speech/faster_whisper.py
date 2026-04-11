"""FasterWhisperSource — транскрипция через faster-whisper Python API.

Новый backend (не port). По умолчанию использует русскую модель
``bzikst/faster-whisper-large-v3-ru-podlodka``. Пишет canonical JSON
(schema v1, только required поля — ADR-8) в ``session_dir/transcripts/``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from domain.annotations import SpeechSegment
from domain.speaker_map import resolve_speaker
from sources.base import Source

# Совпадает с EXCLUDE_AUDIO_PREFIXES из scripts/wisper_launcher.py — craig*
# файлы — это сводный mix track Craig'а, его транскрибировать не нужно.
_EXCLUDE_AUDIO_PREFIXES: tuple[str, ...] = ("craig",)

_CANONICAL_SCHEMA_VERSION = 1
_SOURCE_ENGINE = "faster-whisper"


class FasterWhisperSource(Source):
    """Speech source на основе faster-whisper Python API."""

    name = "faster-whisper"

    def __init__(
        self,
        model: str = "bzikst/faster-whisper-large-v3-ru-podlodka",
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "ru",
        speaker_map: dict[str, str] | None = None,
    ) -> None:
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.speaker_map = speaker_map or {}

    def extract(self, session_dir: Path) -> list[SpeechSegment]:
        """Транскрибировать все аудио в ``session_dir`` через faster-whisper.

        Побочный эффект: пишет canonical JSON на каждый трек в
        ``session_dir/transcripts/<stem>.json``.
        """
        # Lazy import: модуль sources импортируется при старте, но faster-whisper
        # — тяжёлая опциональная зависимость. Держим import локально чтобы
        # sources/__init__.py не падал если пакет не установлен.
        from faster_whisper import WhisperModel

        audio_files = _scan_audio_files(session_dir)
        if not audio_files:
            return []

        transcripts_dir = session_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)

        wm = WhisperModel(self.model, device=self.device, compute_type=self.compute_type)

        all_segments: list[SpeechSegment] = []
        for audio_path in audio_files:
            segments_iter, _info = wm.transcribe(
                str(audio_path),
                language=self.language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            raw_segments = list(segments_iter)
            speaker = resolve_speaker(audio_path.stem, self.speaker_map)

            track_segments: list[SpeechSegment] = []
            for seg in raw_segments:
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

            _write_canonical_json(
                track_segments,
                transcripts_dir / f"{audio_path.stem}.json",
                source_engine=_SOURCE_ENGINE,
            )
            all_segments.extend(track_segments)

        all_segments.sort(key=lambda s: s.start)
        return all_segments


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
