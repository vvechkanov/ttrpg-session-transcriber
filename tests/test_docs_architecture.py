"""The documents that describe *this* repository have to keep describing it.

A design document nobody can check goes stale silently, and the reader cannot
tell which half is still true. These tests check the half a machine can: that
every path a document points at exists, and that the layer the UI actually
lives in is described at all.

They deliberately do not judge prose. A wrong sentence about *why* a layer
exists is for review; a reference to a file deleted four months ago is for a
test.

The path check used to read one file — `ARCHITECTURE.md` — while 47 other
documents named paths nobody verified. The briefs an agent opens first were
among the rotten ones: `scripts/00_README.md` advertised two scripts deleted
in the six-layer move, and both READMEs told the user to edit a `config/`
directory this tree has never contained.
"""

from __future__ import annotations

import functools
import pathlib
import posixpath
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
    "__init__.py": "named as the Python convention — 15 of them, no one in particular",
    # Provisioned, not checked in. `.gitignore` carries both, and the install
    # instructions have to name them anyway — `venv/bin/python` is the
    # interpreter docs/process.md §11 prescribes to the night run.
    "venv": "the virtualenv the user creates; gitignored by design",
    "tools": "the bundled ffmpeg the launcher provisions; gitignored",
    "ffmpeg": "the provisioned binary's own folder, named from inside tools/",
    # Written at runtime next to the user's session, same class as `_cache`.
    "chunks": "written next to the transcript when the chunker runs",
    "session": "a session folder the fixture docs name as an example",
    "games": "the user's tree of session folders, named as an example",
    "e2e_p2": "the fixture directory naming itself from its own README",
    "craig-1": "an example name for a user's Craig export folder",
    "крэйг-2": "the same example, spelled as the user would",
    # The Obsidian vault the `skill/` prompts read. Another tree entirely:
    # these documents ship here but describe files that never live here.
    "Кампейны": "a path in the user's Obsidian vault, not in this repository",
    "Sessions": "the same vault's per-session folders",
    "Glossary": "the same vault's glossary",
    "ttrpg-session-transcriber": "the checkout's own directory, the root of a tree diagram",
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

#: A trailing source line reference: `ui/models/session.py:1349`, and the range
#: form `:1514-1517`. The path half is the claim, exactly as with `::symbol`;
#: without stripping it, the most precise references in the tree — the ones that
#: name the line they mean — would be the only ones reported as broken.
LINE_REFERENCE = re.compile(r":\d+(?:-\d+)?$")

#: A token whose last segment carries no file extension and which does not end
#: in `/` is prose, not a path. `Linux/macOS`, `QML/JS`, `merger/renderer`,
#: `startPct/endPct` and `origin/master` are all "A or B" written with a slash,
#: and every one of them was reported as a missing file the moment this check
#: was pointed at a second document.
#:
#: What it costs, measured rather than guessed, because the first version of
#: this comment named the wrong case and the wrong size:
#:
#: * **A directory written without a trailing slash.** This is the whole of the
#:   loss on `ARCHITECTURE.md` — all eight tokens the rule drops there are
#:   `ui/engines`, `ui/models` and `ui/qml`, real directories, and not one is
#:   prose. Delete `ui/engines/` tomorrow and four lines of §4.1 keep naming it
#:   with the guard green. There is no free fix: nothing distinguishes
#:   `ui/engines` from `merger/renderer` by shape alone.
#: * **A file whose extension is outside :data:`FILE_SUFFIXES`** — 70 in this
#:   tree, most of them `.tsx`, and four of them `.png`. That one *is* fixable
#:   and is fixed: a Markdown link destination skips the rule entirely (see
#:   :func:`_claimed_paths`), because nobody writes `[x](Linux/macOS)`. Without
#:   that, `![shot](docs/screenshots/gone.png)` would have gone unchecked, and
#:   §7.3 of `docs/process.md` asks for screenshots on every UI change.
def _is_path_shaped(token: str) -> bool:
    if token.endswith("/"):
        return True
    last = token.rstrip("/").split("/")[-1]
    return pathlib.PurePath(last).suffix in FILE_SUFFIXES


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

    Every reference resolves from the repository root, bare filenames
    included: `build.spec` means the one at the root, not the different file
    at `launcher/build.spec`. Searching for a matching basename anywhere would
    let the second answer for the first — the document says in §4.2 that these
    are two executables built from two specs, so validating a claim about one
    against the other is worse than not checking it.

    The cost is on the document, and it is the right place for it: a file
    below the root has to be named with its directory. That is a sentence a
    reader can act on, where `Main.qml` alone is a name they have to go
    looking for.

    Directories are matched by prefix, because git lists files and not the
    folders holding them.
    """
    cleaned = token.split("#")[0].rstrip("/")
    if not cleaned:
        return True
    files = _repository_files()
    if cleaned in files:
        return True
    return any(name.startswith(f"{cleaned}/") for name in files)


def _repository_entries() -> frozenset[str]:
    """Top-level names the repository carries, read rather than listed."""
    return frozenset(name.split("/")[0] for name in _repository_files())


def _claimed_paths(text: str, document: str = "") -> list[tuple[int, str]]:
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
    # A Markdown link resolves against the document that carries it, not
    # against the repository root — `[x](README.md)` inside
    # `skill/session-book/SKILL.md` names a file beside *that* file. While only
    # `ARCHITECTURE.md` was read the distinction could not arise, because it
    # sits at the root and the two readings coincide; extending the guard to
    # nested documents is what makes them differ, and reading such a link from
    # the root lets the repository's own `README.md` vouch for a sibling that
    # was never there. Backticked paths keep their root-relative meaning: that
    # is the convention `_exists` documents, and prose says `core/pipeline.py`
    # meaning the one in this tree, wherever the sentence happens to live.
    base = posixpath.dirname(document)
    claims: list[tuple[int, str]] = []
    in_fence = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        # Each candidate carries whether it came from a Markdown link, because
        # a link destination is a path by construction and must not be filtered
        # by shape: `[shot](docs/screenshots/x.png)` names a file whose suffix
        # this module's allowlist does not carry.
        if in_fence:
            candidates = [
                (token, False)
                for token in re.split(r"[\s│┌┐└┘├┤─,;]+", line)
                if "/" in token
            ]
        else:
            candidates = [
                (match.group(1), False)
                for match in re.finditer(r"`([^`\n]+)`", line)
            ]
            candidates += [(token, True) for token in MARKDOWN_LINK.findall(line)]
            candidates += [(token, True) for token in MARKDOWN_REFERENCE.findall(line)]
        for token, from_link in candidates:
            # ``mergers/script_merger.py::ScriptMerger.merge`` — the path half
            # is what this test can check; the symbol half is section 5's job.
            token = token.split("::")[0].strip().rstrip(".,;:)").strip()
            token = LINE_REFERENCE.sub("", token)
            if not token or " " in token:
                continue
            if any(char in token for char in "%<>{}|*'\"=("):
                continue  # an env var, a placeholder, a glob, a line of code
            if from_link:
                # Anchor the destination to its document before anything else
                # looks at it. A link that climbs out of the tree — GitHub's
                # `../../releases` idiom points at the *repository*, not a
                # file — is nobody's path to check.
                token = posixpath.normpath(posixpath.join(base, token))
                if token == ".." or token.startswith("../"):
                    continue
            elif token.startswith(("../", "./")):
                # In backticks a leading `../` is prose or a shell line: the
                # path itself is root-relative by convention, so there is no
                # document to anchor it to.
                continue
            if ":" in token:
                continue  # a URL or a Qt resource: `https://…`, `qrc:/…`
            head = token.split("/")[0]
            if head in NOT_REPOSITORY_PATHS:
                continue
            if "/" in token and not from_link and not _is_path_shaped(token):
                continue  # `Linux/macOS` — prose with a slash in it
            if "/" not in token:
                if token in OUTPUT_FILE_NAMES or not FILE_TOKEN.match(token):
                    continue  # an output file, or a bare word — not a repo path
                if pathlib.PurePath(token).suffix not in FILE_SUFFIXES:
                    continue  # `core.pipeline.run` is a symbol, not a file
            if f"`{token}` (planned)" in line or f"{token} (planned)" in line:
                continue
            claims.append((line_number, token))
    return claims


#: Documents that record what was true when they were written, and are not
#: claims about the tree as it stands. A decision record naming `ui/widgets/`
#: is *correct*: that is the layout the decision was taken against, and editing
#: it to match today would destroy the only reason the record exists.
#:
#: Keyed with a reason each, for the same purpose as :data:`NOT_REPOSITORY_PATHS`
#: — an exclusion nobody has to justify is how a guard quietly stops guarding.
#: This is the larger half of the rot by count — 190 broken paths still inside
#: these documents, against the 25 that were fixed to green the guarded set,
#: both measured with the extractor in this file — and freezing it is a
#: decision, not an oversight: what to do with a document whose subject was
#: deleted is a question for the board, not for this file.
HISTORICAL_PREFIXES = {
    "docs/adr/": "a decision records the tree it was decided against",
    "docs/architecture/": "migration notes describe the layout being migrated away from",
    "docs/handoff/": "a snapshot handed over at a point in time",
    "docs/plans/": "what was planned, including the parts that were not built",
    "docs/specs/": "a point-in-time design spec whose §-numbers are cited from code",
    "docs/design/": "mockup exports and the prompts that produced them",
}

HISTORICAL_DOCUMENTS = {
    "CHANGELOG.md": "a log of what happened; entries name files as they were then",
    "docs/architecture-review-2026-06.md": "a dated review — a snapshot of June",
}


def _markdown_documents() -> list[str]:
    """Every Markdown file the repository carries, in a stable order.

    Git first, the walk as a fallback, for the same reason :func:`_exists`
    works that way — and with the same silence-is-not-emptiness rule.

    The fallback is not theoretical here, and `check=True` would have been a
    worse bug than in `_tracked_files`: this runs inside a `parametrize`
    decorator, at import time. A tree git cannot answer for — a checkout
    unpacked inside someone else's work tree, or git missing entirely — would
    raise during collection and take all of this file's tests down with it,
    including the ones that need no git at all.
    """
    tracked = _tracked_files(PROJECT_ROOT) or _walked_files(PROJECT_ROOT)
    return sorted(name for name in tracked if name.endswith(".md"))


def _live_documents() -> list[str]:
    """The documents whose paths are claims about the repository as it is now.

    Derived by subtraction rather than listed, so a document added tomorrow is
    guarded without anyone remembering to add it here — which is the failure
    this whole card is about.
    """
    return [
        name
        for name in _markdown_documents()
        if name not in HISTORICAL_DOCUMENTS
        and not name.startswith(tuple(HISTORICAL_PREFIXES))
    ]


def _broken_paths_in(document: str) -> list[str]:
    """Slashed paths the document names that the repository does not carry.

    Slashed only: a bare `ci.yml` names a real file without saying where it
    lives, which is a naming policy and a separate card — 152 of them, none of
    them rot.
    """
    text = (PROJECT_ROOT / document).read_text(encoding="utf-8")
    return sorted(
        {
            f"{document}:{line} -> {token}"
            for line, token in _claimed_paths(text, document)
            if "/" in token and not _exists(token)
        }
    )


@pytest.mark.parametrize("document", _live_documents())
def test_every_path_a_live_document_names_exists(document):
    """The card this file grew for: the guard read 1 document out of 48.

    `CONTRIBUTING.md` sent a new contributor to `scripts/asr_backends/`,
    `scripts/merge_whisperx.py` and `scripts/parse_fvtt_chat.py` — all three
    deleted. Both READMEs told the user to edit `config/pathfinder_ru_hotwords.txt`
    in a `config/` directory that has never existed in this tree.
    """
    missing = _broken_paths_in(document)

    assert not missing, f"{document} points at paths that do not exist:\n" + "\n".join(
        missing
    )


def test_the_document_set_is_derived_from_git_not_listed():
    """A document added tomorrow has to be guarded without an edit here.

    The floor on the *guarded* set is the load-bearing half, and it is here
    because mutation found its absence: cutting `_live_documents()` down to
    `["ARCHITECTURE.md", "README.md"]` — the whole card undone, back to very
    nearly the one document it started from — left every test in this file
    green. The only symptom was the collected case count dropping from 52 to
    29, and nothing was watching that. Naming two documents proves membership,
    never coverage.
    """
    documents = _markdown_documents()
    live = _live_documents()

    assert len(documents) > 40, f"suspiciously few documents found: {len(documents)}"
    assert len(live) >= 24, f"the guarded set has shrunk to {len(live)} documents"
    assert "ARCHITECTURE.md" in live
    assert "README.md" in live
    assert "docs/adr/ADR-016-module-ui-contract.md" not in live
    assert "CHANGELOG.md" not in live


def test_every_historical_exclusion_carries_a_reason():
    """Same rule as NOT_REPOSITORY_PATHS: no silent exclusions. A prefix added
    without a reason is how the guard would shrink back to one document."""
    assert all(reason for reason in HISTORICAL_PREFIXES.values())
    assert all(reason for reason in HISTORICAL_DOCUMENTS.values())
    for prefix in HISTORICAL_PREFIXES:
        assert prefix.endswith("/"), f"{prefix} has to be a directory prefix"
    # `all([])` is True, so the two assertions above pass on empty dicts and
    # this test would report a policy that had been deleted as well-formed.
    assert "docs/adr/" in HISTORICAL_PREFIXES
    assert "CHANGELOG.md" in HISTORICAL_DOCUMENTS


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


def test_a_bare_filename_means_a_file_at_the_root():
    """A name with no directory is a claim about the root, and only the root.

    This tree holds two `build.spec` files — one at the root for the runtime,
    one under `launcher/` for the installer — and §4.2 turns on their being
    different. Accepting any matching basename would let the launcher's spec
    vouch for a root spec that had been deleted: the guard would stay green
    across exactly the change it exists to catch."""
    assert _claimed_paths("see `README.md`") == [(1, "README.md")]
    assert _exists("README.md")
    assert _exists("build.spec"), "the runtime spec, at the root"
    assert not _exists("Main.qml"), "lives under ui/qml/ and has to be named so"
    assert _exists("ui/qml/Main.qml")
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


def test_a_link_is_resolved_from_the_document_that_carries_it():
    """Codex on PR #29, and it is the defect that only appears once the guard
    reads more than one document. `[guide](README.md)` inside
    `skill/session-book/SKILL.md` names `skill/session-book/README.md`; read
    from the root, the repository's own `README.md` answers for it and the
    link stays green however broken it is. `ARCHITECTURE.md` never showed this
    because it sits at the root, where both readings agree.

    It cuts the other way too: `../00_README.md` from `scripts/` is a valid
    link that the blanket `../` skip used to drop unchecked, and anchoring it
    brings it back under the guard.
    """
    assert _claimed_paths("[guide](README.md)", "skill/session-book/SKILL.md") == [
        (1, "skill/session-book/README.md")
    ]
    assert _claimed_paths("[a](../00_README.md)", "scripts/00_README.md") == [
        (1, "00_README.md")
    ]
    assert _claimed_paths("[a](ADR-013-gigaam-independent-module.md)", "docs/adr/x.md") == [
        (1, "docs/adr/ADR-013-gigaam-independent-module.md")
    ]
    # Climbing out of the tree is nobody's path, from any depth.
    assert _claimed_paths("[rel](../../releases)", "docs/adr/x.md") == []
    assert _claimed_paths("[rel](../../../escape.md)", "docs/adr/x.md") == []
    # A backticked path stays root-relative wherever the sentence lives.
    assert _claimed_paths("see `core/gone.py`", "skill/session-book/SKILL.md") == [
        (1, "core/gone.py")
    ]
    # And a root document is unchanged — the two readings coincide there.
    assert _claimed_paths("see [ADR](docs/adr/gone.md)", "README.md") == [
        (1, "docs/adr/gone.md")
    ]


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


def test_a_line_reference_names_the_file_it_points_into():
    """`ui/models/session.py:1349` is the most precise kind of reference this
    tree writes, and before the strip it was the only kind reported broken —
    the guard punished exactly the documents that said where they meant."""
    assert _claimed_paths("see `ui/models/session.py:1349`") == [
        (1, "ui/models/session.py")
    ]
    assert _claimed_paths("see `ui/models/session.py:1514-1517`") == [
        (1, "ui/models/session.py")
    ]
    assert _claimed_paths("see `core/no_such_file.py:12`") == [
        (1, "core/no_such_file.py")
    ], "stripping the line must not excuse the file"


def test_prose_with_a_slash_in_it_is_not_a_path():
    """Every one of these was reported as a missing file the moment the check
    was pointed at a second document. A guard that cries about `Linux/macOS`
    teaches its reader to stop reading it."""
    assert _claimed_paths("on `Linux/macOS` the launcher") == []
    assert _claimed_paths("written in `QML/JS`") == []
    assert _claimed_paths("the `merger/renderer` boundary") == []
    assert _claimed_paths("clamped to `0.0/100.0`") == []
    assert _claimed_paths("`git merge origin/master`") == []
    # …and the rule must not swallow a real path: extension, or trailing slash.
    assert _claimed_paths("see `core/gone.py`") == [(1, "core/gone.py")]
    assert _claimed_paths("see `core/gone/`") == [(1, "core/gone/")]


def test_a_link_destination_skips_the_shape_rule():
    """`FILE_SUFFIXES` is an allowlist, and this tree tracks 70 files outside
    it — 56 `.tsx`, and four `.png`. A screenshot is exactly the reference
    `docs/process.md` §7.3 asks every UI change to add, and shape alone would
    stop checking it. A link destination needs no shape test: it is a path
    because of where it is written, not because of how it is spelled."""
    assert _claimed_paths("![shot](docs/screenshots/gone.png)") == [
        (1, "docs/screenshots/gone.png")
    ]
    assert _claimed_paths("[ui]: ui/qml/gone.tsx") == [(1, "ui/qml/gone.tsx")]
    # Backticked, the same token is still shape-filtered — that is the rule
    # this exemption is narrow about, not a hole in it.
    assert _claimed_paths("see `docs/screenshots/gone.png`") == []


def test_a_url_is_not_a_repository_path():
    """`https://github.com/…/x.git` survives the Markdown-link filter when it
    is written in backticks instead, and `qrc:/` is Qt's resource scheme."""
    assert _claimed_paths("clone `https://github.com/o/r.git`") == []
    assert _claimed_paths("loads `qrc:/ui/qml/Main.qml`") == []
    # Carrying an extension on purpose. `../../releases` is turned away by the
    # shape rule before the relative-link rule is ever consulted, so asserting
    # on it proves nothing about the rule it appears to be testing — mutation
    # deleted the `../` skip and these two lines stayed green.
    assert _claimed_paths("see `../../blob/master/TASKS.md`") == []
    assert _claimed_paths("see [roadmap](../../blob/master/TASKS.md)") == []
    assert _claimed_paths("see `../sibling/thing.py`") == []


def test_a_line_of_code_is_not_a_path():
    """Fenced blocks are read for the layer diagrams, and the same fences hold
    Python. `run(Path('games/bogomols/X'` is a call, not a claim."""
    assert _claimed_paths("```\nrun(Path('games/x/Y'))\n```") == []
    assert _claimed_paths("```\nmodel='bzikst/faster-whisper-ru'\n```") == []


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

    The floor sits just under the real count rather than at a token value. It
    was 80 against 138 actual claims, which is not a floor: an entire
    path-heavy section could vanish — 42% of the references — and this would
    still pass, while claiming to catch exactly that. Raise it when the
    document grows; a drop means either the extractor broke or the document
    lost its references, and both are worth failing over.

    It came down from 130 to 125 once the shape rule landed: 137 claims became
    129. The first version of this paragraph said 123 and blamed "fourteen
    prose tokens", and both halves were invented rather than measured — the
    eight tokens actually lost are `ui/engines`, `ui/models` and `ui/qml`
    written without a trailing slash, every one of them a real directory. A
    floor justified by a number nobody ran is the same rot this file exists to
    catch, one level up.
    """
    claims = _claimed_paths(ARCHITECTURE.read_text(encoding="utf-8"))

    assert len(claims) >= 125, f"suspiciously few paths extracted: {len(claims)}"
