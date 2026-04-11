"""Pipeline orchestration: PipelineParams, run(), run_batch().

Core layer entry point. Wires SPEECH_SOURCES → Timeline → Merger → Renderer
and writes the rendered payload to ``session_dir/<output_filename>``.

Does not import ``ui``, tkinter, argparse, or torch directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from core.discovery import find_fvtt_chat_log, find_info_file
from core.gpu_check import check_gpu_or_warn
from domain.annotations import ChatMessage
from domain.timeline import Timeline
from mergers import MERGERS
from renderers import RENDERERS
from sources import SPEECH_SOURCES
from sources.base import Source
from sources.game_log.fvtt_chat import FvttChatSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineParams:
    """Parameters for a single pipeline run."""

    speech_backend: str = "faster-whisper"
    model: str = "bzikst/faster-whisper-large-v3-ru-podlodka"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str = "ru"
    beam_size: int = 10
    merger: str = "script"
    renderer: str = "plain-text"
    output_filename: str = "merged.txt"
    speaker_map: dict[str, str] | None = None


def run(session_dir: Path, params: PipelineParams) -> None:
    """Run the full pipeline on a single session directory.

    Extracts speech + chat, merges via the selected Merger, renders via the
    selected Renderer, and writes the rendered bytes to
    ``session_dir/<params.output_filename>``.
    """
    session_dir = session_dir.resolve()
    if not session_dir.is_dir():
        raise FileNotFoundError(f"session_dir is not a directory: {session_dir}")

    check_gpu_or_warn(params.device)

    speech_cls = SPEECH_SOURCES[params.speech_backend]
    speech_src = speech_cls(**_speech_kwargs(params, speech_cls))
    logger.info("Extracting speech via %s", params.speech_backend)
    speech_segments = speech_src.extract(session_dir)

    chat_log = find_fvtt_chat_log(session_dir)
    chat_messages: list[ChatMessage] = []
    if chat_log is not None:
        info_file = find_info_file(session_dir)
        chat_src = FvttChatSource(chat_log_path=chat_log, info_file_path=info_file)
        logger.info("Extracting FVTT chat from %s", chat_log.name)
        chat_messages = chat_src.extract(session_dir)
    else:
        logger.info("No FVTT chat log found in %s", session_dir)

    timeline = Timeline(
        speech=speech_segments,
        emotions=[],
        chat=chat_messages,
        game_log=[],
    )

    merger = MERGERS[params.merger]()
    events = merger.merge(timeline)

    renderer = RENDERERS[params.renderer]()
    payload = renderer.render(events)

    output_path = session_dir / params.output_filename
    output_path.write_bytes(payload)
    logger.info("Wrote %d bytes to %s", len(payload), output_path)


def run_batch(session_dirs: list[Path], params: PipelineParams) -> None:
    """Process multiple sessions sequentially.

    Failures are logged and skipped, not raised — the batch continues on
    errors so that one bad session does not block the others.
    """
    for session_dir in session_dirs:
        try:
            run(session_dir, params)
        except Exception:
            logger.exception("Session %s failed, continuing batch", session_dir)


def _speech_kwargs(params: PipelineParams, cls: type[Source]) -> dict:
    """Build constructor kwargs for a speech source class.

    Explicit hardcoded mapping — no ``inspect``. FasterWhisperSource does not
    take ``beam_size``; WhisperXSource does.
    """
    if cls.__name__ == "FasterWhisperSource":
        return {
            "model": params.model,
            "device": params.device,
            "compute_type": params.compute_type,
            "language": params.language,
            "speaker_map": params.speaker_map,
        }
    if cls.__name__ == "WhisperXSource":
        return {
            "model": params.model,
            "device": params.device,
            "compute_type": params.compute_type,
            "language": params.language,
            "beam_size": params.beam_size,
            "speaker_map": params.speaker_map,
        }
    raise ValueError(f"unknown speech source class: {cls.__name__}")
