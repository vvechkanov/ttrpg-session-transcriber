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

def _repository_entries() -> frozenset[str]:
    """Top-level names in the working tree, read rather than listed.

    A hand-maintained whitelist would quietly stop checking the day someone
    adds a directory — the guard would still pass while the thing it guards
    rotted. Reading the tree means a new top-level package is covered the
    moment it exists.
    """
    return frozenset(entry.name for entry in PROJECT_ROOT.iterdir() if entry.name != ".git")


def _claimed_paths(text: str) -> list[tuple[int, str]]:
    """Every backticked token that points at something inside this repository.

    A token counts as a claim when its first segment names a real top-level
    entry — so `build.spec` and `core/pipeline.py` are both checked, while
    `src/` (the layout ADR-10 rejected), `session_dir/_cache/` (created at
    runtime under the user's session folder), `%LOCALAPPDATA%/models/` and
    `merged.txt` are not. Without that rule the document could not name
    anything it does not itself ship.

    Fenced blocks are read too, because the layer diagrams live there and
    that is exactly where a stale path survived longest: `ui/gui.py` sat in
    the §3 diagram for months while every prose mention of it was corrected.
    Inside a fence only slashed tokens count — a bare ``cli.py`` in a box has
    no directory to check it against.

    A path may be marked as not-yet-existing by appending ``(planned)``:

        | 6 | `sources/emotion/` (planned) | … |

    Without that escape a roadmap cannot name the file it plans to add, and
    the test would quietly delete the plan instead of checking the document.
    """
    entries = _repository_entries()
    claims: list[tuple[int, str]] = []
    in_fence = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            candidates = [
                token for token in re.split(r"[\s│┌┐└┘├┤─,;]+", line) if "/" in token
            ]
        else:
            candidates = [match.group(1) for match in re.finditer(r"`([^`\n]+)`", line)]
        for token in candidates:
            # ``mergers/script_merger.py::ScriptMerger.merge`` — the path half
            # is what this test can check; the symbol half is section 5's job.
            token = token.split("::")[0].strip().rstrip(".,;:)").strip()
            if not token or " " in token:
                continue
            if token.split("/")[0] not in entries:
                continue
            if f"`{token}` (planned)" in line or f"{token} (planned)" in line:
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


def test_a_planned_path_may_be_named_without_existing_yet():
    """Otherwise the roadmap cannot name the file it plans to add, and the
    only way to green the test is to delete the plan — which is how the P5
    and P6 rows lost their file lists in the first place."""
    assert _claimed_paths("| 6 | `sources/emotion/` (planned) | … |") == []
    assert _claimed_paths("| 6 | `sources/emotion/` | … |") == [(1, "sources/emotion/")]


def test_paths_inside_fenced_blocks_are_checked():
    """The layer diagrams live in fences, and that is where `ui/gui.py`
    survived every prose correction for months."""
    fenced = "```\n│  ui/gui.py, core/nope.py  │\n```"

    assert sorted(token for _, token in _claimed_paths(fenced)) == [
        "core/nope.py",
        "ui/gui.py",
    ]


def test_a_root_level_file_is_checked_too():
    """`build.spec` has no slash in it, and a rule keyed on slashes would let
    the document point at a root-level file that is not there."""
    assert _claimed_paths("built by `build.spec`") == [(1, "build.spec")]
    assert _claimed_paths("writes `merged.txt`") == []


def test_repository_roots_are_read_from_disk_not_listed():
    """The whole point of deriving them: a directory added tomorrow is covered
    without anyone remembering to update this file."""
    entries = _repository_entries()

    assert {"core", "ui", "tests", "docs", "build.spec"} <= entries
    assert ".git" not in entries


def test_the_extractor_reads_the_real_document():
    """And that it is pointed at a document with paths in it at all.

    The floor sits just under the real count rather than at a token value: a
    guard that passes after two thirds of the references vanish is not
    guarding much. Raise it when the document grows; a drop means either the
    extractor broke or the document lost its references — both worth failing
    over.
    """
    claims = _claimed_paths(ARCHITECTURE.read_text(encoding="utf-8"))

    assert len(claims) >= 80, f"suspiciously few paths extracted: {len(claims)}"
