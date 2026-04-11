"""CLI entry point: argparse → PipelineParams → core.run_batch."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from core import PipelineParams, run, run_batch
from core.speaker_map import load_speaker_map
from sources import SPEECH_SOURCES  # only for argparse choices=

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ttrpg-session-transcriber",
        description="Transcribe Craig per-speaker audio tracks and merge with optional FVTT chat log.",
    )
    ap.add_argument(
        "session_dirs",
        nargs="+",
        help="One or more session folders (each containing per-speaker *.flac).",
    )
    ap.add_argument(
        "--speech_backend",
        default="faster-whisper",
        choices=sorted(SPEECH_SOURCES.keys()),
        help="Speech backend (default: faster-whisper).",
    )
    ap.add_argument("--model", default="bzikst/faster-whisper-large-v3-ru-podlodka")
    ap.add_argument("--language", default="ru")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute_type", default="float16")
    ap.add_argument("--beam_size", type=int, default=10)
    ap.add_argument(
        "--chunk",
        action="store_true",
        help="After merge, split merged.txt into overlapping chunks via scripts/chunk_text.py.",
    )
    ap.add_argument("--chunk_chars", type=int, default=40000)
    ap.add_argument("--chunk_overlap", type=float, default=0.20)

    # Soft-dropped flags: accepted for one release, ignored with warning.
    for dropped in ("--vad_method", "--hf_token"):
        ap.add_argument(dropped, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--diarize", action="store_true", help=argparse.SUPPRESS)

    return ap


def _warn_ignored_flags(args: argparse.Namespace) -> None:
    ignored: list[str] = []
    if args.vad_method is not None:
        ignored.append("--vad_method")
    if args.hf_token is not None:
        ignored.append("--hf_token")
    if args.diarize:
        ignored.append("--diarize")
    for flag in ignored:
        logger.warning("%s is ignored in the new pipeline — see P3 roadmap", flag)


def _run_chunk_post_step(session_dir: Path, chunk_chars: int, chunk_overlap: float) -> None:
    chunk_script = Path(__file__).resolve().parents[1] / "scripts" / "chunk_text.py"
    if not chunk_script.exists():
        logger.warning("chunk_text.py not found at %s, skipping chunking", chunk_script)
        return
    merged_txt = session_dir / "merged.txt"
    if not merged_txt.exists():
        logger.warning("merged.txt not found for chunking: %s", merged_txt)
        return
    cmd = [
        sys.executable,
        str(chunk_script),
        str(merged_txt),
        "--chunk_chars",
        str(chunk_chars),
        "--overlap",
        str(chunk_overlap),
    ]
    logger.info("Chunking %s", merged_txt)
    subprocess.run(cmd, cwd=str(session_dir), check=True)


def cli_main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    args = _build_parser().parse_args()
    _warn_ignored_flags(args)

    session_dirs = [Path(p).expanduser().resolve() for p in args.session_dirs]
    for d in session_dirs:
        if not d.is_dir():
            print(f"Error: session_dir not found: {d}", file=sys.stderr)
            return 2

    # Load speaker map from the FIRST session dir (CLI does not edit it).
    speaker_map = load_speaker_map(session_dirs[0])

    params = PipelineParams(
        speech_backend=args.speech_backend,
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=args.language,
        beam_size=args.beam_size,
        speaker_map=speaker_map or None,
    )

    if len(session_dirs) == 1:
        try:
            run(session_dirs[0], params)
        except Exception:
            logger.exception("Pipeline failed for %s", session_dirs[0])
            return 1
    else:
        run_batch(session_dirs, params)

    if args.chunk:
        for d in session_dirs:
            try:
                _run_chunk_post_step(d, args.chunk_chars, args.chunk_overlap)
            except subprocess.CalledProcessError:
                logger.exception("chunk_text.py failed for %s", d)

    return 0
