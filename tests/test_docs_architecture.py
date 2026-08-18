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

import pathlib
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = PROJECT_ROOT / "ARCHITECTURE.md"

#: First segments that are deliberately *not* paths in this tree. Everything
#: else that looks like a path gets checked — including a misspelling like
#: ``sorces/`` and a package that used to exist and was deleted, which is the
#: whole class of rot this file guards against.
#:
#: Keyed on the first segment, with a reason each, because an unexplained
#: exclusion here is how a guard quietly stops guarding.
NOT_REPOSITORY_PATHS = {
    "src": "ADR-10 names it as the layout that was rejected",
    "session_dir": "created at runtime under the user's session folder",
    "_cache": "same, written next to the session",
    "if": "`if/else` is prose, not a path",
    "bzikst": "a HuggingFace model id, not a file",
}

#: Slash-less tokens that name a file the pipeline *writes*, not one this
#: repository contains. Everything else with a file extension is a claim —
#: whitelisting extensions instead would stop checking `README.md` the day it
#: were renamed, which is the same rot in a different spot.
OUTPUT_FILE_NAMES = frozenset(
    {"merged.txt", "speaker_map.json", "__init__.py", "settings.ini", "uninstall.exe"}
)

#: What "looks like a file" means for a token with no directory in it.
FILE_TOKEN = re.compile(r"^[\w.\-]+\.[A-Za-z0-9]{1,6}$")


def _repository_suffixes() -> frozenset[str]:
    """File extensions that actually occur in this tree.

    This is what separates `README.md` from `core.pipeline.run`: both are
    dotted words, but only one of them ends in something this repository
    stores. Derived rather than listed, for the same reason as the roots.
    """
    return frozenset(
        path.suffix
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file() and path.suffix and ".git" not in path.parts
    )


def _exists(token: str) -> bool:
    """Whether the document's path points at something in the tree.

    A token with a directory in it is resolved from the repository root. A
    bare filename cannot be — `Main.qml` lives under `ui/qml/` — so it counts
    as present when a file of that name exists anywhere.
    """
    if "/" in token:
        return (PROJECT_ROOT / token.rstrip("/")).exists()
    return any(path.name == token for path in PROJECT_ROOT.rglob(token))


def _repository_entries() -> frozenset[str]:
    """Top-level names in the working tree, read rather than listed."""
    return frozenset(entry.name for entry in PROJECT_ROOT.iterdir() if entry.name != ".git")


def _claimed_paths(text: str) -> list[tuple[int, str]]:
    """Every backticked token that points at something inside this repository.

    Anything shaped like a path is a claim unless it is explicitly excused in
    :data:`NOT_REPOSITORY_PATHS` or carries a shell/URL marker. Keying on
    "first segment exists in the tree" instead would be exactly backwards: a
    typo (`sorces/base.py`) or a package deleted whole (`old_pkg/thing.py`)
    would stop being checked at the moment it became wrong.

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
    suffixes = _repository_suffixes()
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
            if any(char in token for char in "%<>{}|*"):
                continue  # an environment variable, a placeholder, a glob
            head = token.split("/")[0]
            if head in NOT_REPOSITORY_PATHS:
                continue
            if "/" not in token:
                if token in OUTPUT_FILE_NAMES or not FILE_TOKEN.match(token):
                    continue  # an output file, or a bare word — not a repo path
                if pathlib.PurePath(token).suffix not in suffixes:
                    continue  # `core.pipeline.run` is a symbol, not a file
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
            if not _exists(token)
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


def test_a_bare_filename_is_checked_wherever_it_lives():
    """`README.md` and `Main.qml` are named without a directory. Keying on a
    list of "config-ish" extensions would stop checking a Markdown document
    the day it were renamed — the same rot, one spot over."""
    assert _claimed_paths("see `README.md`") == [(1, "README.md")]
    assert _claimed_paths("the shell is `Main.qml`") == [(1, "Main.qml")]
    assert _exists("Main.qml"), "lives under ui/qml/, still counts as present"
    assert not _exists("no_such_document.md")


def test_a_dotted_symbol_is_not_a_filename():
    """`core.pipeline.run` and `README.md` are both dotted words; only one of
    them ends in something this tree stores."""
    assert _claimed_paths("call `core.pipeline.run`") == []
    assert _claimed_paths("read `sys.argv`") == []
    assert _claimed_paths("implement `Renderer.render`") == []


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


def test_a_misspelled_or_deleted_package_is_still_a_claim():
    """The rule that matters. Keying on "the first segment exists" would stop
    checking a path at the exact moment it became wrong — a typo, or a package
    deleted whole, would read as "not one of ours" and be waved through."""
    assert _claimed_paths("see `sorces/base.py`") == [(1, "sorces/base.py")]
    assert _claimed_paths("see `old_package/thing.py`") == [(1, "old_package/thing.py")]


def test_the_excusals_are_the_only_way_out():
    """Each entry in NOT_REPOSITORY_PATHS carries a reason, so an exclusion
    cannot be added silently."""
    assert all(reason for reason in NOT_REPOSITORY_PATHS.values())
    assert _claimed_paths("`%LOCALAPPDATA%/models/` on Windows") == []
    assert _claimed_paths("`session_dir/_cache/{sources|mergers}/x.json`") == []


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
