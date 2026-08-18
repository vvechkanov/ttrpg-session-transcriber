"""ARCHITECTURE.md has to describe *this* repository.

A design document nobody can check goes stale silently, and the reader cannot
tell which half is still true. These tests check the half a machine can: that
every path the document points at exists, and that the layer the UI actually
lives in is described at all.

They deliberately do not judge prose. A wrong sentence about *why* a layer
exists is for review; a reference to a file deleted four months ago is for a
test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = PROJECT_ROOT / "ARCHITECTURE.md"

#: Top-level directories of this repository. A backticked token starting with
#: one of these is a claim *about this tree*, and so has to be true.
#:
#: Anything else in backticks is left alone on purpose: `src/` appears in
#: ADR-10 as the layout that was rejected, `session_dir/_cache/` is a runtime
#: directory under the user's session folder, `%LOCALAPPDATA%/models/` is a
#: Windows location, and `if/else` is not a path at all. Checking those would
#: force the document to stop naming anything it does not ship.
REPO_ROOTS = frozenset(
    {"core", "domain", "sources", "mergers", "renderers", "ui", "launcher",
     "scripts", "tests", "docs", "prompts", "licenses", "skill", ".github"}
)


def _claimed_paths(text: str) -> list[tuple[int, str]]:
    """Every backticked token that points at a path inside this repository."""
    claims: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in re.finditer(r"`([^`\n]+)`", line):
            token = match.group(1).strip()
            # ``mergers/script_merger.py::ScriptMerger.merge`` — the path half
            # is what this test can check; the symbol half is section 5's job.
            token = token.split("::")[0].strip()
            if not token or " " in token or "/" not in token:
                continue
            if token.split("/")[0] not in REPO_ROOTS:
                continue
            claims.append((line_number, token))
    return claims


def test_every_path_architecture_names_exists():
    """The regression this file was written for: the document still pointed at
    `scripts/wisper_launcher.py`, `scripts/merge_whisperx.py` and
    `core/timeline.py` — one deleted in the six-layer move, one replaced by
    `mergers/script_merger.py`, one that ADR-12 itself says lives in
    `domain/`. An agent reviewing "the domain ↔ core ↔ asr_backends boundary"
    checked it against a directory that had not existed for months."""
    text = ARCHITECTURE.read_text(encoding="utf-8")

    missing = sorted(
        {
            f"{ARCHITECTURE.name}:{line} -> {token}"
            for line, token in _claimed_paths(text)
            if not (PROJECT_ROOT / token.rstrip("/")).exists()
        }
    )

    assert not missing, "ARCHITECTURE.md points at paths that do not exist:\n" + "\n".join(
        missing
    )


@pytest.mark.parametrize("package", ["ui/models", "ui/engines", "ui/qml"])
def test_architecture_describes_the_ui_sublayers(package):
    """The whole UI layer was missing from the document while being the part
    under active work."""
    text = ARCHITECTURE.read_text(encoding="utf-8")

    assert package in text, f"ARCHITECTURE.md never mentions {package}"


def test_the_extractor_finds_a_broken_reference():
    """A guard on the guard. The extractor skips everything that is not a repo
    path, so an over-eager skip rule would leave the check green while reading
    nothing — the failure mode that makes a test worse than no test."""
    assert _claimed_paths("see `core/no_such_file.py` for details") == [
        (1, "core/no_such_file.py")
    ]
    assert _claimed_paths("`session_dir/_cache/` is created at runtime") == []
    assert _claimed_paths("the `src/` layout was rejected") == []


def test_the_extractor_reads_the_real_document():
    """And that it is pointed at a document with paths in it at all."""
    claims = _claimed_paths(ARCHITECTURE.read_text(encoding="utf-8"))

    assert len(claims) >= 20, f"suspiciously few paths extracted: {len(claims)}"
