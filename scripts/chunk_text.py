#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Split a large merged transcript (merged.txt) into overlapping chunks.

Default strategy:
- split by blank lines (paragraphs)
- build chunks by target character size
- overlap is applied in paragraphs (last N paragraphs of previous chunk are
  included at the start of the next chunk)

It also writes:
- 000_context.txt (speaker list + helpful notes)
- manifest.json (chunk boundaries and basic stats)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_speakers_from_text(text: str) -> list[str]:
    speakers = []
    seen = set()
    for line in text.splitlines():
        # "Speaker: text"
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
    speaker_map = load_speaker_map(session_dir)
    speakers = extract_speakers_from_text(text)

    lines = []
    lines.append(f"Session folder: {session_dir}")
    lines.append(f"Source file: {merged_path.name}")
    lines.append("")

    if speaker_map:
        lines.append("Speakers (from speaker_map.json):")
        for key, v in speaker_map.items():
            if not isinstance(v, dict):
                continue
            player = (v.get("player") or "").strip()
            character = (v.get("character") or "").strip()
            role = (v.get("role") or "").strip()
            label = " / ".join([x for x in [player, character] if x])
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
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    # split by 1+ blank lines
    parts = re.split(r"\n\s*\n+", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_paragraphs(
    paras: list[str],
    *,
    chunk_chars: int,
    overlap_ratio: float,
) -> list[dict]:
    chunks: list[dict] = []
    i = 0

    while i < len(paras):
        start_i = i
        cur = []
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
            # pathological: one paragraph bigger than chunk_chars
            cur = [paras[i]]
            start_i = i
            i += 1
            end_i = i

        overlap_n = int(round(len(cur) * overlap_ratio))
        overlap_n = max(0, min(overlap_n, len(cur) - 1))  # never overlap 100%

        chunks.append(
            {
                "start_paragraph": start_i,
                "end_paragraph": end_i,
                "paragraph_count": len(cur),
                "approx_chars": cur_chars,
                "overlap_paragraphs": overlap_n,
                "text": "\n\n".join(cur).strip() + "\n",
            }
        )

        # move pointer back for overlap
        if end_i >= len(paras):
            break
        i = max(end_i - overlap_n, start_i + 1)

    return chunks


def main() -> int:
    ap = argparse.ArgumentParser(prog="chunk_text.py")
    ap.add_argument("merged_txt", help="Path to merged.txt")
    ap.add_argument("--out_dir", default=None, help="Output folder (default: <session_dir>\\chunks)")
    ap.add_argument("--chunk_chars", type=int, default=40000, help="Target chunk size in characters (default: 40000)")
    ap.add_argument("--overlap", type=float, default=0.20, help="Overlap ratio [0..0.5] (default: 0.20)")

    args = ap.parse_args()

    merged_path = Path(args.merged_txt).expanduser().resolve()
    session_dir = merged_path.parent
    if not merged_path.exists():
        raise SystemExit(f">>> merged.txt not found: {merged_path}")

    overlap = float(args.overlap)
    if overlap < 0:
        overlap = 0.0
    if overlap > 0.5:
        overlap = 0.5

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else (session_dir / "chunks")
    out_dir.mkdir(parents=True, exist_ok=True)

    text = read_text(merged_path)
    paras = split_paragraphs(text)
    if not paras:
        raise SystemExit(">>> merged.txt is empty (no paragraphs found).")

    chunks = chunk_paragraphs(paras, chunk_chars=int(args.chunk_chars), overlap_ratio=overlap)

    # context
    (out_dir / "000_context.txt").write_text(
        format_context(session_dir, merged_path, text),
        encoding="utf-8",
    )

    manifest = {
        "source_file": str(merged_path),
        "out_dir": str(out_dir),
        "chunk_chars": int(args.chunk_chars),
        "overlap": overlap,
        "paragraphs_total": len(paras),
        "chunks_total": len(chunks),
        "chunks": [],
    }

    for idx, ch in enumerate(chunks, start=1):
        fname = f"{idx:04d}.txt"
        wrapped = []
        wrapped.append("=== CHUNK START ===")
        wrapped.append(f"chunk: {idx:04d}")
        wrapped.append(f"source: {merged_path.name}")
        wrapped.append(f"paragraphs: {ch['start_paragraph']}..{ch['end_paragraph']-1} (count {ch['paragraph_count']}, overlap {ch['overlap_paragraphs']})")
        wrapped.append("")
        wrapped.append(ch["text"].rstrip())
        wrapped.append("")
        wrapped.append("=== CHUNK END ===")
        wrapped.append("")
        (out_dir / fname).write_text("\n".join(wrapped), encoding="utf-8")
        manifest["chunks"].append(
            {
                "file": fname,
                "start_paragraph": ch["start_paragraph"],
                "end_paragraph": ch["end_paragraph"],
                "paragraph_count": ch["paragraph_count"],
                "approx_chars": ch["approx_chars"],
                "overlap_paragraphs": ch["overlap_paragraphs"],
            }
        )

    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. Wrote {len(chunks)} chunks to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
