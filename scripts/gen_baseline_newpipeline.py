#!/usr/bin/env python3
"""
Generate expected_merged.txt baseline for e2e_p2 using the NEW pipeline.

Baseline = freeze-today output of core.run() with faster-whisper backend,
CPU/int8/beam=1 for determinism. This is the regression baseline for future
refactors (not legacy equivalence proof — that's Tier 3 manual step).

Usage:
    python scripts/gen_baseline_newpipeline.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FIXTURE_SESSION_DIR = PROJECT_ROOT / "tests" / "fixtures" / "e2e_p2" / "session"
EXPECTED_MERGED = PROJECT_ROOT / "tests" / "fixtures" / "e2e_p2" / "expected_merged.txt"


def main() -> int:
    from core.pipeline import PipelineParams, run

    # Validate fixtures exist
    flac_files = sorted(FIXTURE_SESSION_DIR.glob("*.flac"))
    if not flac_files:
        print("ERROR: No .flac files found in session dir.", file=sys.stderr)
        print("Run: python scripts/gen_fixtures_noprint.py", file=sys.stderr)
        return 1

    print(f"Found {len(flac_files)} FLAC files:")
    for f in flac_files:
        print(f"  {f.name}: {f.stat().st_size} bytes")

    params = PipelineParams(
        speech_backend="faster-whisper",
        model="bzikst/faster-whisper-large-v3-ru-podlodka",
        device="cpu",
        compute_type="int8",
        language="ru",
        beam_size=1,
        output_filename="merged.txt",
    )

    print("\nRunning new pipeline (this may take several minutes on CPU)...")
    print(f"  model: {params.model}")
    print(f"  device: {params.device}  compute_type: {params.compute_type}  beam_size: {params.beam_size}")

    try:
        run(FIXTURE_SESSION_DIR, params)
    except Exception as e:
        print(f"ERROR: pipeline.run() failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    merged_src = FIXTURE_SESSION_DIR / "merged.txt"
    if not merged_src.exists():
        print("ERROR: merged.txt was not produced.", file=sys.stderr)
        return 1

    content = merged_src.read_text(encoding="utf-8")
    lines = content.splitlines()
    print(f"\n=== Pipeline output ({len(lines)} lines, {merged_src.stat().st_size} bytes) ===")
    for line in lines[:20]:
        print(f"  {line}")
    if len(lines) > 20:
        print(f"  ... ({len(lines) - 20} more lines)")

    # Copy as the frozen baseline
    shutil.copy2(merged_src, EXPECTED_MERGED)
    print(f"\nBaseline written: {EXPECTED_MERGED.name} ({EXPECTED_MERGED.stat().st_size} bytes)")
    print("\nFirst 10 lines of expected_merged.txt:")
    for line in EXPECTED_MERGED.read_text(encoding="utf-8").splitlines()[:10]:
        print(f"  {line}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
