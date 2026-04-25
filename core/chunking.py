"""Post-processing: slice a merged transcript into overlapping chunks.

Split ``merged.txt`` into numbered chunks small enough to feed into an
LLM prompt, plus a context header and a manifest. Overlap is applied
at paragraph granularity so summaries of adjacent chunks can be
deduplicated without losing mid-paragraph spans.

Originally ``scripts/chunk_text.py``; moved here so the CLI can call
it directly instead of spawning a subprocess (the subprocess path
broke under PyInstaller where ``sys.executable`` points at the bundle
exe and ``scripts/`` is not included in the bundle).

Pure / deterministic — no UI or subprocess dependencies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_speakers_from_text(text: str) -> list[str]:
    """Return speaker labels in first-seen order.

    A line qualifies as speaker-prefixed when it matches
    ``"<short label>: <rest>"``; good enough for Craig + Whisper output
    where the merger prefixes every cue with the resolved speaker.
    """

    speakers: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^([^:\n]{1,80}):\s+.+", line)
        if not m:
            continue
        s = m.group(1).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        speakers.append(s)
    return speakers


def load_speaker_map(session_dir: Path) -> dict:
    p = session_dir / "speaker_map.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(read_text(p))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def format_context(session_dir: Path, merged_path: Path, text: str) -> str:
    """Human-readable header for the chunks directory.

    Lists the session folder, source filename, and — if available —
    the speaker map from ``speaker_map.json`` or the speakers parsed
    from the transcript.
    """

    speaker_map = load_speaker_map(session_dir)
    speakers = extract_speakers_from_text(text)

    lines: list[str] = []
    lines.append(f"Session folder: {session_dir}")
    lines.append(f"Source file: {merged_path.name}")
    lines.append("")

    if speaker_map:
        lines.append("Speakers (from speaker_map.json):")
        for key, v in speaker_map.items():
            if not isinstance(v, dict):
                continue
            player = (v.get("player") or "").strip()
            # Accept both new shape (`characters: [...]`) and legacy
            # (`character: "..."`). `load_speaker_map` here reads the
            # raw file without normalization, so chunking may still see
            # the legacy shape on pre-migration files.
            raw_characters = v.get("characters")
            if isinstance(raw_characters, list):
                characters = [
                    str(c).strip()
                    for c in raw_characters
                    if isinstance(c, str) and str(c).strip()
                ]
            elif isinstance(v.get("character"), str) and v["character"].strip():
                characters = [v["character"].strip()]
            else:
                characters = []
            role = (v.get("role") or "").strip()
            rendered_characters = " / ".join(characters)
            label = " / ".join([x for x in [player, rendered_characters] if x])
            if not label:
                label = key
            if role:
                label += f" [{role}]"
            lines.append(f"- {key}: {label}")
        lines.append("")
    elif speakers:
        lines.append("Speakers (detected from merged.txt):")
        for s in speakers:
            lines.append(f"- {s}")
        lines.append("")

    lines.append("Notes:")
    lines.append("- Chunks overlap on purpose: repeated paragraphs help preserve context across boundaries.")
    lines.append("- When summarizing chunk-by-chunk, deduplicate overlaps while merging the summaries.")
    return "\n".join(lines).strip() + "\n"


def split_paragraphs(text: str) -> list[str]:
    """Normalise line endings and split on one-or-more blank lines."""

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    parts = re.split(r"\n\s*\n+", text)
    return [p.strip() for p in parts if p.strip()]


@dataclass(frozen=True)
class ChunkingOptions:
    """Post-render chunking knobs, forwarded from UI preferences.

    ``enabled`` controls whether :func:`core.pipeline.run` invokes
    :func:`chunk_text_file` after the render stage. The other two
    fields map 1:1 onto the kwargs of :func:`chunk_text_file`.
    """

    enabled: bool = False
    chunk_chars: int = 40_000
    overlap_ratio: float = 0.20


@dataclass(frozen=True)
class Chunk:
    start_paragraph: int
    end_paragraph: int
    paragraph_count: int
    approx_chars: int
    overlap_paragraphs: int
    text: str


def chunk_paragraphs(
    paras: list[str],
    *,
    chunk_chars: int,
    overlap_ratio: float,
) -> list[Chunk]:
    """Pack paragraphs into chunks ~``chunk_chars`` long with N-paragraph overlap.

    The overlap count is computed as ``round(len(chunk) * overlap_ratio)``
    and is clamped so two adjacent chunks always advance by at least
    one paragraph (prevents infinite loops on huge paragraphs).
    """

    chunks: list[Chunk] = []
    i = 0

    while i < len(paras):
        start_i = i
        cur: list[str] = []
        cur_chars = 0

        while i < len(paras):
            p = paras[i]
            add = len(p) + (2 if cur else 0)  # blank line between paras
            if cur and (cur_chars + add) > chunk_chars:
                break
            cur.append(p)
            cur_chars += add
            i += 1

        end_i = i
        if not cur:
            # Pathological: one paragraph bigger than chunk_chars.
            cur = [paras[i]]
            start_i = i
            i += 1
            end_i = i

        overlap_n = int(round(len(cur) * overlap_ratio))
        overlap_n = max(0, min(overlap_n, len(cur) - 1))

        chunks.append(
            Chunk(
                start_paragraph=start_i,
                end_paragraph=end_i,
                paragraph_count=len(cur),
                approx_chars=cur_chars,
                overlap_paragraphs=overlap_n,
                text="\n\n".join(cur).strip() + "\n",
            )
        )

        if end_i >= len(paras):
            break
        i = max(end_i - overlap_n, start_i + 1)

    return chunks


def chunk_text_file(
    merged_path: Path,
    *,
    chunk_chars: int = 40_000,
    overlap_ratio: float = 0.20,
    out_dir: Path | None = None,
) -> Path:
    """Write chunks + ``000_context.txt`` + ``manifest.json``.

    Args:
        merged_path: path to the ``merged.txt`` (or any plain-text file).
        chunk_chars: target chunk size in characters; final chunks may
            be slightly smaller to respect paragraph boundaries.
        overlap_ratio: fraction of paragraphs from the tail of a chunk
            that seed the start of the next one. Clamped to ``[0, 0.5]``.
        out_dir: destination directory; defaults to
            ``<merged_path>.parent / "chunks"``. Created if missing.

    Returns:
        Path to the directory that received the chunks.

    Raises:
        FileNotFoundError: if ``merged_path`` doesn't exist.
        ValueError: if the file is empty (no paragraphs).
    """

    merged_path = merged_path.expanduser().resolve()
    if not merged_path.exists():
        raise FileNotFoundError(f"merged file not found: {merged_path}")

    session_dir = merged_path.parent

    overlap = float(overlap_ratio)
    if overlap < 0:
        overlap = 0.0
    if overlap > 0.5:
        overlap = 0.5

    dest = out_dir.expanduser().resolve() if out_dir else (session_dir / "chunks")
    dest.mkdir(parents=True, exist_ok=True)

    text = read_text(merged_path)
    paras = split_paragraphs(text)
    if not paras:
        raise ValueError(f"merged file is empty (no paragraphs): {merged_path}")

    chunks = chunk_paragraphs(paras, chunk_chars=int(chunk_chars), overlap_ratio=overlap)

    (dest / "000_context.txt").write_text(
        format_context(session_dir, merged_path, text),
        encoding="utf-8",
    )

    manifest: dict = {
        "source_file": str(merged_path),
        "out_dir": str(dest),
        "chunk_chars": int(chunk_chars),
        "overlap": overlap,
        "paragraphs_total": len(paras),
        "chunks_total": len(chunks),
        "chunks": [],
    }

    for idx, ch in enumerate(chunks, start=1):
        fname = f"{idx:04d}.txt"
        wrapped: list[str] = []
        wrapped.append("=== CHUNK START ===")
        wrapped.append(f"chunk: {idx:04d}")
        wrapped.append(f"source: {merged_path.name}")
        wrapped.append(
            f"paragraphs: {ch.start_paragraph}..{ch.end_paragraph - 1} "
            f"(count {ch.paragraph_count}, overlap {ch.overlap_paragraphs})"
        )
        wrapped.append("")
        wrapped.append(ch.text.rstrip())
        wrapped.append("")
        wrapped.append("=== CHUNK END ===")
        wrapped.append("")
        (dest / fname).write_text("\n".join(wrapped), encoding="utf-8")
        manifest["chunks"].append(
            {
                "file": fname,
                "start_paragraph": ch.start_paragraph,
                "end_paragraph": ch.end_paragraph,
                "paragraph_count": ch.paragraph_count,
                "approx_chars": ch.approx_chars,
                "overlap_paragraphs": ch.overlap_paragraphs,
            }
        )

    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return dest
