"""Tier 2 — Semantic e2e regression gate.

Runs the NEW pipeline (core.run + faster-whisper) on the synthetic fixture audio
in tests/fixtures/e2e_p2/session/ and compares the output to the frozen baseline
tests/fixtures/e2e_p2/expected_merged.txt via token overlap (>= 0.90).

SKIP CONDITIONS:
  - @pytest.mark.slow: excluded from default CI run (pytest -m "not slow")
  - @pytest.mark.requires_asr: needs faster-whisper model downloaded

RUN LOCALLY:
  pytest tests/test_e2e_tier2_semantic.py -v -m slow

XFAIL CONDITION:
  If expected_merged.txt does not exist, the test is marked xfail (baseline not
  yet generated). Generate it with:
    python scripts/gen_baseline_newpipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SESSION_DIR = PROJECT_ROOT / "tests" / "fixtures" / "e2e_p2" / "session"
EXPECTED_MERGED = PROJECT_ROOT / "tests" / "fixtures" / "e2e_p2" / "expected_merged.txt"
BASELINE_EXISTS = EXPECTED_MERGED.exists() and EXPECTED_MERGED.stat().st_size > 10

# Insert project root so imports work without package install
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Token overlap helper
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Split text into lowercase word tokens, stripping punctuation."""
    import re
    return re.findall(r"\w+", text.lower())


def _token_overlap(a: str, b: str) -> float:
    """Symmetric token overlap: 2 * |intersection| / (|A| + |B|).

    Returns 1.0 for identical texts, 0.0 for completely different.
    Tolerates ASR variance, punctuation drift, whitespace differences.
    """
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)

    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0

    set_a = set(tokens_a)
    set_b = set(tokens_b)
    intersection = set_a & set_b
    return 2 * len(intersection) / (len(tokens_a) + len(tokens_b))


# ---------------------------------------------------------------------------
# Fixtures availability guard
# ---------------------------------------------------------------------------

def _flac_files_exist() -> bool:
    if not FIXTURE_SESSION_DIR.exists():
        return False
    return len(list(FIXTURE_SESSION_DIR.glob("*.flac"))) == 3


# ---------------------------------------------------------------------------
# Tier 2 test
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.requires_asr
@pytest.mark.xfail(
    not BASELINE_EXISTS,
    reason=(
        "expected_merged.txt baseline not yet generated. "
        "Run: python scripts/gen_baseline_newpipeline.py"
    ),
    strict=False,
)
@pytest.mark.skipif(
    not _flac_files_exist(),
    reason=(
        "FLAC fixtures not found in tests/fixtures/e2e_p2/session/. "
        "Run: python scripts/gen_fixtures_noprint.py"
    ),
)
def test_tier2_semantic_token_overlap():
    """Full pipeline run on fixture audio produces output with >= 0.90 token overlap vs baseline.

    Strategy:
    1. Run core.run() on the e2e_p2 session dir with CPU/int8/beam=1
    2. Read the produced merged.txt
    3. Compare to frozen expected_merged.txt via token overlap
    4. Assert overlap >= 0.90

    The 0.90 threshold tolerates minor ASR drift between model versions and
    runs, while catching regressions in the merger/renderer logic.
    """
    from core.pipeline import PipelineParams, run

    # Run pipeline with deterministic settings
    params = PipelineParams(
        speech_backend="faster-whisper",
        model="bzikst/faster-whisper-large-v3-ru-podlodka",
        device="cpu",
        compute_type="int8",
        language="ru",
        beam_size=1,
        output_filename="merged_tier2_test.txt",
    )

    run(FIXTURE_SESSION_DIR, params)

    actual_path = FIXTURE_SESSION_DIR / "merged_tier2_test.txt"
    assert actual_path.exists(), f"Pipeline did not produce output at {actual_path}"

    actual = actual_path.read_text(encoding="utf-8")
    baseline = EXPECTED_MERGED.read_text(encoding="utf-8")

    assert actual.strip(), "Pipeline produced empty output"

    overlap = _token_overlap(actual, baseline)
    print(f"\nToken overlap: {overlap:.3f} (threshold: 0.90)")
    print(f"Actual length: {len(actual)} chars, {len(_tokenize(actual))} tokens")
    print(f"Baseline length: {len(baseline)} chars, {len(_tokenize(baseline))} tokens")
    print(f"\nActual (first 500 chars):\n{actual[:500]}")
    print(f"\nBaseline (first 500 chars):\n{baseline[:500]}")

    assert overlap >= 0.90, (
        f"Token overlap {overlap:.3f} is below threshold 0.90. "
        "This indicates a regression in the pipeline output. "
        "Diff actual vs baseline for details."
    )


# ---------------------------------------------------------------------------
# Structural sub-checks (always-pass sanity on the output format)
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.requires_asr
@pytest.mark.skipif(
    not _flac_files_exist(),
    reason="FLAC fixtures not found — run scripts/gen_fixtures_noprint.py",
)
def test_tier2_output_format():
    """Pipeline output lines conform to 'Speaker: text' format.

    Note: PipelineParams(speaker_map=None) means the pipeline uses audio stem
    names as speaker labels (e.g. '1-test_gm') rather than display names.
    That is correct pipeline behavior; speaker_map resolution is opt-in.
    """
    import re

    from core.pipeline import PipelineParams, run

    params = PipelineParams(
        speech_backend="faster-whisper",
        model="bzikst/faster-whisper-large-v3-ru-podlodka",
        device="cpu",
        compute_type="int8",
        language="ru",
        beam_size=1,
        output_filename="merged_tier2_format_test.txt",
    )

    run(FIXTURE_SESSION_DIR, params)

    actual_path = FIXTURE_SESSION_DIR / "merged_tier2_format_test.txt"
    actual = actual_path.read_text(encoding="utf-8")

    assert actual.strip(), "Pipeline produced empty output"

    # Expect track stem names as speaker labels (pipeline uses stems when speaker_map=None)
    expected_stems = {"1-test_gm", "2-test_player", "3-test_player2"}
    found_stems = [stem for stem in expected_stems if stem in actual]
    assert found_stems, (
        f"No expected track stems found in output. "
        f"Expected any of: {expected_stems}. "
        f"Output starts with: {actual[:300]}"
    )

    # Every non-empty line must match the format: "Label: text" or "[ЧАТ] Label: text"
    line_pattern = re.compile(r"^(\[ЧАТ\] )?[^:]+: .+$")
    non_empty_lines = [ln for ln in actual.splitlines() if ln.strip()]
    malformed = [ln for ln in non_empty_lines if not line_pattern.match(ln)]
    assert not malformed, (
        f"Malformed output lines (not matching 'Speaker: text' format):\n"
        + "\n".join(malformed[:5])
    )
