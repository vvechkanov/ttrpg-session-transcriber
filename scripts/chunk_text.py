#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thin CLI wrapper around :func:`core.chunking.chunk_text_file`.

Kept for users who run the chunker standalone on an existing
``merged.txt`` without re-running the pipeline. The real logic lives
in :mod:`core.chunking` so the main CLI (``python -m ui ... --chunk``)
and this script stay in lockstep — no code duplication, no drift.

Run::

    python scripts/chunk_text.py path/to/merged.txt \\
        --chunk_chars 40000 --overlap 0.20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running the script from any CWD by putting the repo root on
# sys.path before importing. The wrapper lives in scripts/, so the
# root is one level up.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.chunking import chunk_text_file  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="chunk_text.py")
    ap.add_argument("merged_txt", help="Path to merged.txt")
    ap.add_argument(
        "--out_dir",
        default=None,
        help="Output folder (default: <session_dir>/chunks)",
    )
    ap.add_argument(
        "--chunk_chars",
        type=int,
        default=40_000,
        help="Target chunk size in characters (default: 40000)",
    )
    ap.add_argument(
        "--overlap",
        type=float,
        default=0.20,
        help="Overlap ratio [0..0.5] (default: 0.20)",
    )

    args = ap.parse_args()

    try:
        dest = chunk_text_file(
            Path(args.merged_txt),
            chunk_chars=args.chunk_chars,
            overlap_ratio=args.overlap,
            out_dir=Path(args.out_dir) if args.out_dir else None,
        )
    except FileNotFoundError as exc:
        raise SystemExit(f">>> {exc}") from exc
    except ValueError as exc:
        raise SystemExit(f">>> {exc}") from exc

    print(f"Done. Wrote chunks to: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
