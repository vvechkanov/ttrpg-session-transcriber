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

import functools
import pathlib
import re
import shutil
import subprocess
import sys
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
    {"merged.txt", "speaker_map.json", "settings.ini", "uninstall.exe"}
)

#: What "looks like a file" means for a token with no directory in it.
FILE_TOKEN = re.compile(r"^[\w.\-]+\.[A-Za-z0-9]{1,6}$")

#: Extensions that make a dotted token a filename rather than a symbol.
#: `README.md` and `core.pipeline.run` are both dotted words; only the vocabulary
#: of file types tells them apart, and it has to be a fixed list rather than
#: "extensions currently in the tree" — otherwise deleting the last `.spec`
#: file would stop `build.spec` being checked.
#:
#: The limit is real and worth naming: an invented extension (`README.mdx`)
#: reads as a symbol and is skipped. Slashed paths and Markdown links carry no
#: such ambiguity and are checked unconditionally, which is where the bulk of
#: the document's references live.
FILE_SUFFIXES = frozenset(
    {".md", ".py", ".qml", ".js", ".json", ".txt", ".toml", ".ini", ".cfg",
     ".spec", ".yml", ".yaml", ".ps1", ".bat", ".sh", ".exe", ".zip"}
)

#: Directories to skip when git cannot answer (see :func:`_walked_files`).
#: Only a fallback: `.gitignore` covers far more than any hand-kept list, which
#: is exactly why the primary source is git and not this set.
NOT_THE_REPOSITORY = frozenset(
    {".git", "venv", ".venv", "__pycache__", "node_modules", "build", "dist",
     ".pytest_cache", ".ruff_cache", ".mypy_cache", "tools", ".eggs"}
)

#: A relative Markdown link target: `[text](docs/adr/thing.md)`, not `[t](http…)`
#: and not `[t](#anchor)`.
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\((?!https?:|mailto:|#)([^)\s]+)\)")

#: A reference-style Markdown definition: `[ui]: docs/adr/thing.md`. The use
#: site (`[ADR][ui]`) names no path at all, so the definition is the only place
#: the destination can be checked — and renaming its target would otherwise
#: leave this guard green.
#: The whole line has to be the definition — destination plus an optional
#: title — or prose swallows it: a CommonMark footnote (`[^1]: и/или так`) and
#: a quoted line (`[Кто-то]: он/она сделал`) both otherwise donate their first
#: slashed word to the check as a "path".
MARKDOWN_REFERENCE = re.compile(
    r"^\s{0,3}\[(?!\^)[^\]^]+\]:\s*<?(?!https?:|mailto:|#)([^>\s]+)>?"
    r"(?:\s+[\"'(][^\n]*)?\s*$"
)


def _tracked_files(root: Path) -> frozenset[str] | None:
    """Repository-relative paths git tracks *and* has on disk, or `None`.

    Git is the authority on what this repository *contains*. Walking the
    filesystem instead lets anything ignored answer for a reference the
    repository itself has lost — `.gitignore` here excludes `.claude/`,
    `/handoff/`, `Тестовое/`, `venv/` and generated fixture transcripts, and a
    dead `foo.py` stays "present" as long as any of them ships that name.

    `git ls-files` reads the *index*, not the disk, so the two are intersected:
    without that a file deleted from the tree but still staged would read as
    present, which is a check the filesystem walk used to make. The remaining
    asymmetry is deliberate and worth knowing: a brand-new file the document
    already references counts as missing until it is `git add`-ed.

    `None` means git had nothing to say — not installed, or a directory it
    does not track (a checkout unpacked inside someone else's work tree, or a
    fresh `git init` before the first `add`). An empty listing is that same
    silence, not an empty repository, and must not be mistaken for one: the
    caller falls back to :func:`_walked_files`.
    """
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError):
        return None
    tracked = frozenset(
        name for name in listed.stdout.split("\0") if name and (root / name).exists()
    )
    return tracked or None


def _walked_files(root: Path) -> frozenset[str]:
    """Fallback for a tree git does not know: walk it, prune the obvious.

    Pruning is keyed on the path *below* the root — a checkout that happens to
    live in a directory called `build/` or `venv/` is still a checkout, and
    matching against absolute parts would erase the whole tree.
    """
    below_root = (path.relative_to(root) for path in root.rglob("*") if path.is_file())
    return frozenset(
        relative.as_posix()
        for relative in below_root
        if NOT_THE_REPOSITORY.isdisjoint(relative.parts)
    )


@functools.lru_cache(maxsize=None)
def _files_under(root: Path) -> frozenset[str]:
    tracked = _tracked_files(root)
    return _walked_files(root) if tracked is None else tracked


def _repository_files() -> frozenset[str]:
    """Every file this repository actually carries, as relative posix paths."""
    return _files_under(PROJECT_ROOT)


def _exists(token: str) -> bool:
    """Whether the document's path points at something the repository carries.

    A bare filename has no directory to resolve against — `Main.qml` lives
    under `ui/qml/` — so it counts as present when a tracked file of that name
    exists anywhere. Directories are matched by prefix, because git lists
    files and not the folders holding them.
    """
    cleaned = token.split("#")[0].rstrip("/")
    if not cleaned:
        return True
    files = _repository_files()
    if cleaned in files:
        return True
    if any(name.startswith(f"{cleaned}/") for name in files):
        return True
    if "/" in cleaned:
        return False
    return any(name.rsplit("/", 1)[-1] == cleaned for name in files)


def _repository_entries() -> frozenset[str]:
    """Top-level names the repository carries, read rather than listed."""
    return frozenset(name.split("/")[0] for name in _repository_files())


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
            candidates += MARKDOWN_LINK.findall(line)
            candidates += MARKDOWN_REFERENCE.findall(line)
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
                if pathlib.PurePath(token).suffix not in FILE_SUFFIXES:
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


def test_a_markdown_link_destination_is_a_claim():
    """`[ADR](docs/adr/gone.md)` names a path just as much as a backticked one,
    and renaming the target would otherwise leave the guard green."""
    assert _claimed_paths("see [ADR](docs/adr/gone.md)") == [(1, "docs/adr/gone.md")]
    assert _claimed_paths("see [ADR](docs/adr/ADR-017-ui-toolkit-pyside6.md)") == [
        (1, "docs/adr/ADR-017-ui-toolkit-pyside6.md")
    ]
    assert _claimed_paths("see [site](https://example.com/a.md)") == []
    assert _claimed_paths("see [section](#anchor)") == []


def test_a_reference_style_definition_is_a_claim():
    """`[ADR][ui]` names no path; its `[ui]: docs/adr/…` definition does, and
    it is the only place the destination can be checked at all."""
    assert _claimed_paths("[ui]: docs/adr/gone.md") == [(1, "docs/adr/gone.md")]
    assert _claimed_paths('[ui]: docs/adr/gone.md "Title"') == [(1, "docs/adr/gone.md")]
    assert _claimed_paths("[site]: https://example.com/a.md") == []
    assert _claimed_paths("[top]: #anchor") == []
    # A definition is the whole line. Prose shaped like one is not, or every
    # footnote and every quoted line donates its first slashed word as a path.
    assert _claimed_paths("[^1]: и/или так, см. примечание") == []
    assert _claimed_paths("[Кто-то сказал]: он/она сделал") == []


def _init_repository(root: Path) -> None:
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "t"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)


needs_git = pytest.mark.skipif(
    shutil.which("git") is None, reason="proves the git path; the fallback covers the rest"
)


@needs_git
def test_git_decides_what_the_repository_contains(tmp_path, monkeypatch):
    """The hand-kept skip list can only ever name what someone remembered.
    `.gitignore` excludes `.claude/`, `/handoff/`, `Тестовое/` and generated
    fixture output too, so a deleted file stays "present" as long as any
    ignored directory happens to ship its name. Git knows the difference;
    exercised against a real repository so the claim is proved, not asserted.

    Every name here is one this repository does *not* contain, so the test
    fails rather than passes if the monkeypatch ever stops taking effect."""
    _init_repository(tmp_path)
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "only_in_the_fixture.py").write_text("", encoding="utf-8")
    (tmp_path / "handoff").mkdir()
    (tmp_path / "handoff" / "impostor.py").write_text("", encoding="utf-8")
    subprocess.run(
        ["git", "add", "core/only_in_the_fixture.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(sys.modules[_exists.__module__], "PROJECT_ROOT", tmp_path)

    assert _exists("core/only_in_the_fixture.py")
    assert _exists("core/")
    assert not _exists("handoff/impostor.py"), "on disk, but git does not track it"
    assert not _exists("impostor.py"), "bare name found only in an untracked file"


@needs_git
def test_a_tree_git_does_not_track_falls_back_instead_of_failing(tmp_path, monkeypatch):
    """`git ls-files` exits 0 with nothing to say in two situations that are
    not "an empty repository": a checkout unpacked inside someone else's work
    tree, and a fresh `git init` before the first `add`. Reading that silence
    as "this repository contains no files" fails every single path at once."""
    _init_repository(tmp_path)
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "pipeline.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys.modules[_exists.__module__], "PROJECT_ROOT", tmp_path)

    assert _tracked_files(tmp_path) is None, "silence, not an empty repository"
    assert _exists("core/pipeline.py"), "the walk answers when git will not"


@needs_git
def test_a_file_only_in_the_index_is_not_on_disk(tmp_path, monkeypatch):
    """`git ls-files` reads the index. Without intersecting it with the tree a
    file deleted but still staged would read as present — a check the plain
    filesystem walk used to make, and losing it would make this guard weaker
    than the one it replaced."""
    _init_repository(tmp_path)
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "gone.py").write_text("", encoding="utf-8")
    (tmp_path / "core" / "here.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "core"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "core" / "gone.py").unlink()
    monkeypatch.setattr(sys.modules[_exists.__module__], "PROJECT_ROOT", tmp_path)

    assert _exists("core/here.py")
    assert not _exists("core/gone.py"), "staged, but no longer in the tree"


def test_existence_ignores_anything_outside_the_repository(tmp_path, monkeypatch):
    """The fallback for a tree git cannot answer for. With the prescribed
    in-tree `venv/`, a dependency shipping a file of the same name would
    otherwise keep a dead reference looking alive."""
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "pipeline.py").write_text("", encoding="utf-8")
    (tmp_path / "venv" / "lib").mkdir(parents=True)
    (tmp_path / "venv" / "lib" / "impostor.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys.modules[_exists.__module__], "PROJECT_ROOT", tmp_path)

    assert _exists("core/pipeline.py")
    assert _exists("core/")
    assert not _exists("venv/lib/impostor.py"), "path inside a pruned directory"
    assert not _exists("impostor.py"), "bare name found only inside venv/"


def test_the_fallback_prunes_below_the_root_not_above_it(tmp_path, monkeypatch):
    """A checkout that happens to sit in a directory called `build/` is still a
    checkout. Matching the skip list against absolute path parts erases the
    whole tree instead of a subdirectory of it — and since git is the primary
    source now, this walk is the only thing left to catch the difference."""
    root = tmp_path / "build" / "proj"
    (root / "core").mkdir(parents=True)
    (root / "core" / "pipeline.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys.modules[_exists.__module__], "PROJECT_ROOT", root)

    assert _exists("core/pipeline.py"), "the root's own name is not a skip rule"


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


def test_repository_roots_are_derived_not_listed():
    """The whole point of deriving them: a directory added tomorrow is covered
    without anyone remembering to update this file."""
    entries = _repository_entries()

    assert {"core", "ui", "tests", "docs", "build.spec"} <= entries


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
