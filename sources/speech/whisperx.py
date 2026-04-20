"""WhisperXSource — обёртка над whisperx CLI через subprocess.

Verbatim port из ``scripts/wisper_launcher.py`` (строки ~642-651) —
legacy backend, сохранён как regression baseline на время P2.
После subprocess читает JSON который whisperx записал в ``output_dir``,
парсит как ``merge_whisperx.load_segments``, конвертирует в
``SpeechSegment`` и перезаписывает canonical JSON (schema v1, только
required поля — ADR-8).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from domain.annotations import SpeechSegment
from domain.speaker_map import resolve_speaker
from sources.base import Source

# Те же что и у faster_whisper — дублирование намеренное, cleanup пост-P2.
_EXCLUDE_AUDIO_PREFIXES: tuple[str, ...] = ("craig",)

_CANONICAL_SCHEMA_VERSION = 1
_SOURCE_ENGINE = "whisperx"


class WhisperXSource(Source):
    """Speech source — обёртка subprocess вызова whisperx CLI."""

    name = "whisperx"

    def __init__(
        self,
        model: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "ru",
        beam_size: int = 10,
        speaker_map: dict[str, str] | None = None,
    ) -> None:
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.speaker_map = speaker_map or {}

    def extract(self, session_dir: Path) -> list[SpeechSegment]:
        """Запустить whisperx на каждом треке сессии, вернуть SpeechSegment-ы."""
        audio_files = _scan_audio_files(session_dir)
        if not audio_files:
            return []

        transcripts_dir = session_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)

        all_segments: list[SpeechSegment] = []
        for audio_path in audio_files:
            # Verbatim port of scripts/wisper_launcher.py:642-651 (gui_main path).
            cmd = [
                "whisperx",
                str(audio_path),
                "--model",
                self.model,
                "--language",
                self.language,
                "--output_dir",
                str(transcripts_dir),
                "--vad_method",
                "silero",
                "--device",
                self.device,
                "--compute_type",
                self.compute_type,
                "--beam_size",
                str(self.beam_size),
            ]
            subprocess.run(cmd, cwd=str(transcripts_dir), check=True)

            # whisperx пишет "<stem>.json" в output_dir.
            produced = transcripts_dir / f"{audio_path.stem}.json"
            if not produced.exists():
                raise RuntimeError(
                    f"whisperx did not create expected JSON: {produced}"
                )

            speaker = resolve_speaker(audio_path.stem, self.speaker_map)
            track_segments = _load_whisperx_json(produced, speaker)

            # Нормализуем поверх того что написал whisperx: перезаписываем
            # файл как canonical JSON schema v1 (ADR-8).
            _write_canonical_json(
                track_segments,
                transcripts_dir / f"{audio_path.stem}.json",
                source_engine=_SOURCE_ENGINE,
            )
            all_segments.extend(track_segments)

        all_segments.sort(key=lambda s: s.start)
        return all_segments


def _scan_audio_files(session_dir: Path, pattern: str = "*.flac") -> list[Path]:
    """Port из ``scripts/wisper_launcher.py:_scan_audio_files`` (дублирован намеренно)."""
    return sorted(
        p
        for p in session_dir.glob(pattern)
        if not any(
            p.stem.lower() == x or p.stem.lower().startswith(x + "-")
            for x in _EXCLUDE_AUDIO_PREFIXES
        )
    )


def _load_whisperx_json(path: Path, speaker: str) -> list[SpeechSegment]:
    """Парсинг whisperx JSON → list[SpeechSegment].

    Port из ``scripts/merge_whisperx.py:load_segments`` — те же имена полей,
    тот же фильтр пустых текстов. Без дополнительных проверок.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    segs = data.get("segments", [])
    out: list[SpeechSegment] = []
    for seg in segs:
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue
        out.append(
            SpeechSegment(
                start=float(seg["start"]),
                end=float(seg["end"]),
                speaker=speaker,
                text=txt,
                confidence=None,
            )
        )
    return out


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
