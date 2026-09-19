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
#: Compared against a *case-folded* suffix, so every entry here is written in
#: lower case and `core/GONE.PY` is the same kind of claim as `core/gone.py`.
#: `.markdown` is carried for one reason only: :func:`_markdown_documents`
#: selects documents by that spelling too, and a vocabulary that admits a file
#: as a document while refusing to recognise a path pointing at it is an
#: exception nobody wrote down — the shape this file keeps finding rot in.
#: "Path" rather than "link", precisely: a Markdown link destination skips
#: the shape rule altogether, so `[x](notes.markdown)` is a claim with this
#: entry and without it. What the entry buys is the backticked and the fenced
#: spelling.
#:
#: Only one of the two routes here reaches it, and the other is not worth
#: looking for: :data:`FILE_TOKEN` caps an extension at six characters, so a
#: bare backticked `notes.markdown` is refused two rules earlier and the
#: vocabulary is never consulted. What this entry changes is
#: :func:`_is_path_shaped`, that is a token with a directory in it.
FILE_SUFFIXES = frozenset(
    {".md", ".markdown", ".py", ".qml", ".js", ".json", ".txt", ".toml",
     ".ini", ".cfg", ".spec", ".yml", ".yaml", ".ps1", ".bat", ".sh", ".exe",
     ".zip"}
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
    return pathlib.PurePath(last).suffix.lower() in FILE_SUFFIXES


#: A relative Markdown link target: `[text](docs/adr/thing.md)`, not `[t](http…)`
#: and not `[t](#anchor)`.
#: One level of balanced parentheses is allowed inside the destination, because
#: `[design](docs/ui_(draft).md)` is a legal link and `[^)\s]+` stops at the
#: first `)` — handing the check `docs/ui_(draft`, a path nobody wrote.
#: The optional title — `[guide](docs/guide.md "Guide")` — has to be consumed
#: too, or the link yields no candidate at all and deleting its target leaves
#: the guard green.
#: A title is delimited by one of three pairs, and each may contain the other
#: two: the first attempt excluded *both* quote characters from every title
#: whatever its delimiter, so `"It's gone"` and `'A "Guide"'` — ordinary
#: English inside ordinary CommonMark — yielded no candidate at all, and the
#: parenthesised form was not known. The delimiter is captured and matched
#: against itself instead.
MARKDOWN_LINK = re.compile(
    r"\[[^\]]*\]\((?!https?:|mailto:|#)((?:[^()\s]|\([^()\s]*\))+)"
    r"(?:\s+(?:([\"'])[^\n]*?\2|\([^()]*\)))?\)"
)

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

#: The optional title that may follow a link destination, in either spelling:
#: `[guide](docs/guide.md "Guide")` and `[ui]: docs/guide.md "Guide"`. Matched
#: from the end of the destination so :func:`_is_planned` can step over it and
#: reach the `(planned)` marker beyond.
TRAILING_LINK_TITLE = re.compile(
    r"^\s+(?:([\"'])[^\n]*?\1|\((?!planned\))[^()]*\))"
)

#: An opening or closing code fence: three or more backticks or tildes. The
#: run is captured whole rather than tested three characters at a time,
#: because both its character and its length decide what closes it.
FENCE_MARKER = re.compile(r"(`{3,}|~{3,})")


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


def _is_planned(line: str, end_of_path: int) -> bool:
    """Whether `(planned)` excuses the path that ends at `end_of_path`.

    Bound to the occurrence rather than looked for anywhere on the line. A
    search of the whole line excuses *every* copy of a path as soon as one is
    marked: in ``[future](docs/future.md) (planned); [now](docs/future.md)``
    the second link is an unqualified claim about today and was waved through
    by the first one's marker.

    The spellings differ only in what sits between the path and the marker — a
    closing backtick, a closing bracket, a title, or nothing — so the position
    is taken at the end of the path itself and whatever separates the two is
    stepped over. The link case was missed for as long as only
    `ARCHITECTURE.md` was read: it carries no such links.

    A title has to be stepped over explicitly rather than lumped in with the
    punctuation, because it can contain anything: `[design](docs/future.md
    "Draft") (planned)` and `[ui]: docs/future.md "Draft" (planned)` both put
    the marker beyond it, and a roadmap that titles its link was failing the
    guard until the file it plans to add existed — a false red produced by the
    one rule whose entire job is to prevent one.
    """
    rest = TRAILING_LINK_TITLE.sub("", line[end_of_path:], count=1)
    return rest.lstrip("`)>").startswith(" (planned)")


def _claims_with_origin(
    text: str, document: str = ""
) -> list[tuple[int, str, bool]]:
    """Every claimed path, with whether it came from a Markdown link.

    The flag matters to the caller as well as here: a link destination is a
    path by construction, so the "slashed paths only" boundary — which exists
    to keep *bare backticked filenames* out of scope — must not apply to it.
    `[TASKS.md](TASKS.md)` is an unambiguous claim about a root file, and
    dropping it let a rename break every such link with the guard green.

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
    # The exact marker run that opened the block being read, or `None`. Both
    # halves of it are load-bearing, and each was found missing in turn.
    #
    # The *character*, because CommonMark has two fences and a block closes
    # only on its own: `~~~` exists precisely so a block may contain
    # backticks, and reading the ``` line inside one as a closing fence turns
    # the rest of the block into prose. Tracking only ``` left every path in a
    # tilde-fenced tree diagram unread.
    #
    # The *length*, for the same reason one level in: a block opened with four
    # backticks exists so that a three-backtick line may sit inside it, and a
    # closing run has to be at least as long as the one that opened.
    fence: str | None = None
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        # A Windows spelling is the same claim about the same file, and the
        # instructions in this tree are written in both: every `venv\\Scripts`
        # line has a POSIX twin one row above it. Only the twin was read.
        #
        # Normalised here, on the line, *before* it is split into tokens —
        # not on the token after it has been classified. Inside a fence a
        # token becomes a candidate by carrying a slash at all, so a
        # backslashed path is discarded before any rule about filenames is
        # reached; folding later would leave that branch unchanged and the
        # path still unread. The replacement is one character for one, so
        # every offset — and with it the `(planned)` marker's position —
        # survives it.
        #
        # What it cannot tell apart, named rather than discovered later: a
        # backslash escaping Markdown punctuation. A backticked
        # `docs/a\\_b.md` becomes the claim `docs/a/_b.md`, which is nobody's
        # file and would be reported broken. No live document writes one
        # today — the four escapes in this tree (`\\|` twice in
        # `ARCHITECTURE.md`, `\\_` in `FEATURE_REQUESTS.md`, an escaped
        # backtick in `docs/process.md`) each die on a space, on the `|`
        # filter, or on sitting outside a code span — so this is the shape of
        # the first false red rather than one. Telling the two apart means
        # asking what follows the backslash, and punctuation is a legal first
        # character of a filename too (`scripts\\_helper.py`), so it is a
        # trade rather than a fix, and it is a card.
        line = raw_line.replace("\\", "/")
        stripped = line.lstrip()
        run = FENCE_MARKER.match(stripped)
        if run is not None:
            marker = run.group(1)
            if fence is None:
                fence = marker
                continue
            # A closing fence carries nothing but the marker. ```python is an
            # *opening* fence's info string, and a line shaped like one inside
            # a block is content — closing on it hands the rest of the block
            # to the prose reader, which is the miss this fence work exists to
            # remove.
            if (
                marker[0] == fence[0]
                and len(marker) >= len(fence)
                and not stripped[len(marker):].strip()
            ):
                fence = None
                continue
            # A shorter run, the other character, or an info string: content.
        in_fence = fence is not None
        # Each candidate carries whether it came from a Markdown link, because
        # a link destination is a path by construction and must not be filtered
        # by shape: `[shot](docs/screenshots/x.png)` names a file whose suffix
        # this module's allowlist does not carry.
        # Each candidate carries where its path ends in the line, so the
        # `(planned)` marker can be bound to this occurrence and not to a
        # different copy of the same path further along.
        candidates: list[tuple[str, bool, int]] = []
        if in_fence:
            cursor = 0
            for token in re.split(r"[\s│┌┐└┘├┤─,;]+", line):
                if not token:
                    continue
                found = line.find(token, cursor)
                cursor = (found if found >= 0 else cursor) + len(token)
                if "/" in token:
                    candidates.append((token, False, cursor))
        else:
            for match in re.finditer(r"`([^`\n]+)`", line):
                candidates.append((match.group(1), False, match.end(1)))
            # A code span shows Markdown rather than writing it: a document
            # explaining the `(planned)` escape spells out a whole link to
            # illustrate it, and read as a link that example becomes a claim
            # the document never made — a false red, and on a document whose
            # only sin is documenting this very file. The span is blanked
            # rather than cut so that every offset, and with it the
            # `(planned)` marker's position, survives untouched.
            outside_code = re.sub(
                r"`[^`\n]+`", lambda m: " " * len(m.group(0)), line
            )
            for match in MARKDOWN_LINK.finditer(outside_code):
                candidates.append((match.group(1), True, match.end(1)))
            for match in MARKDOWN_REFERENCE.finditer(outside_code):
                candidates.append((match.group(1), True, match.end(1)))
        for token, from_link, path_ends_at in candidates:
            # ``mergers/script_merger.py::ScriptMerger.merge`` — the path half
            # is what this test can check; the symbol half is section 5's job.
            token = token.split("::")[0].strip().rstrip(".,;:)").strip()
            token = LINE_REFERENCE.sub("", token)
            if not token or " " in token:
                continue
            # A shell line continued onto the next row ends in a lone
            # backslash, which the normalisation above turns into a lone
            # slash: `CONTRIBUTING.md:115` is exactly that. It would not have
            # been reported either — `_exists` strips a trailing slash and
            # answers `True` for the empty string left behind — so the claim
            # passes for the wrong reason and pads every count built on this
            # list. A separator with nothing on either side of it is not a
            # path anyone wrote.
            if not token.strip("/"):
                continue
            if from_link:
                # A destination is a URL reference, so it can carry a query as
                # well as a fragment: `docs/example.md?raw=1` names a file that
                # exists, and checking the literal string fails CI on a valid
                # link — a false red, the one failure mode worse than a miss.
                #
                # Stripped here, *before* the character filters below, and not
                # after them: a query is made of percent-escapes, so
                # `docs/gone.md?value=%2A` was thrown out as a placeholder and
                # its target could be deleted with the guard green. The filters
                # are about the path, and this is where the path begins.
                token = token.split("#", 1)[0].split("?", 1)[0]
                if not token:
                    continue
            if any(char in token for char in "%<>{}|*"):
                continue  # an environment variable, a placeholder, a glob
            if not from_link and any(char in token for char in "'\"=("):
                # A line of code caught in a fence: `run(Path('games/x/Y'))`.
                # A link destination is already delimited by its own brackets,
                # so the same characters there are part of a filename — and
                # dropping it would leave a broken link unreported.
                continue
            if from_link:
                # A leading slash is resolved against the *site*, not against
                # this checkout, and both spellings of it land outside: `//x`
                # borrows the page's scheme, and `/README.md` in a document
                # GitHub renders points at `github.com/README.md`. Reading
                # either as a repository path lets the root file of the same
                # name vouch for a link that resolves somewhere else entirely
                # — and the first draft of this rule did exactly that, having
                # been written to tell the two apart rather than to notice
                # that neither is ours.
                if token.startswith("/"):
                    continue
                # Anchor the destination to its document. A link that climbs
                # out of the tree — GitHub's `../../releases` idiom, which
                # only escapes from a root document and is only written
                # there — is nobody's path to check.
                token = posixpath.normpath(posixpath.join(base, token))
                if token == ".." or token.startswith("../"):
                    continue
                # `normpath` turns `./` — "the directory I am in" — into `.`,
                # which names no file and would be reported missing.
                if token == ".":
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
                if token in OUTPUT_FILE_NAMES:
                    continue  # written next to the session, not carried here
                if not from_link:
                    # Both rules exist to tell a *backticked* token apart from
                    # prose, where nothing else can: `core.pipeline.run` and
                    # `README.md` are the same shape, and `pytest` is a word.
                    # A link destination needs no such tiebreak — it is a path
                    # by construction, the same reason the shape rule skips it
                    # — and asking it for an extension dropped every link to
                    # the root `LICENSE`: `[LICENSE](LICENSE)` in `README.md`
                    # and `README.ru.md`, `[MIT License](LICENSE)` in
                    # `CONTRIBUTING.md`.
                    if not FILE_TOKEN.match(token):
                        continue  # a bare word — not a repository path
                    if pathlib.PurePath(token).suffix.lower() not in FILE_SUFFIXES:
                        continue  # `core.pipeline.run` is a symbol, not a file
            if _is_planned(line, path_ends_at):
                continue
            claims.append((line_number, token, from_link))
    return claims


def _claimed_paths(text: str, document: str = "") -> list[tuple[int, str]]:
    """:func:`_claims_with_origin` without the origin flag."""
    return [(line, token) for line, token, _ in _claims_with_origin(text, document)]


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

    The extension is matched case-blind, and `.markdown` counts as well.
    Nothing in this tree is spelled either way today, so this is prevention
    rather than rot — but the failure it prevents is the silent kind: a
    document left out of the set is not reported as anything, it is simply
    never checked, and the guard stays green while the file rots.
    """
    tracked = _tracked_files(PROJECT_ROOT) or _walked_files(PROJECT_ROOT)
    return sorted(
        name for name in tracked if name.lower().endswith((".md", ".markdown"))
    )


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

    Slashed only, *unless the path came from a Markdown link*: a bare `ci.yml`
    in backticks names a real file without saying where it lives, which is a
    naming policy and a separate card — 152 of them, none of them rot. A link
    is not that case. `[TASKS.md](TASKS.md)` says exactly which file it means,
    and skipping it for want of a slash let a rename of `TASKS.md` break the
    links in `README.md`, `CONTRIBUTING.md` and `TASKS.md` itself while this
    guard stayed green.
    """
    text = (PROJECT_ROOT / document).read_text(encoding="utf-8")
    return sorted(
        {
            f"{document}:{line} -> {token}"
            for line, token, from_link in _claims_with_origin(text, document)
            if (from_link or "/" in token) and not _exists(token)
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


def test_the_planned_marker_reaches_a_markdown_link_too():
    """Codex on PR #29. `[design](docs/future.md) (planned)` puts a closing
    bracket between the destination and the marker, so the escape matched
    nothing and a roadmap linking to a file it plans to add failed the guard.
    Invisible while only `ARCHITECTURE.md` was read — it has no such links.

    Matched against the destination as written, because by the time the path
    has been anchored to its document it no longer occurs in the line."""
    assert _claimed_paths("[design](docs/future.md) (planned)") == []
    assert _claimed_paths("[design](docs/future.md)") == [(1, "docs/future.md")]
    assert _claimed_paths("[ui]: docs/future.md (planned)") == []
    # The marker travels with its own line, not with the whole document.
    assert _claimed_paths("[design](docs/future.md)\nand `core/gone.py`") == [
        (1, "docs/future.md"),
        (2, "core/gone.py"),
    ]
    # A nested document: the destination is anchored, the marker still lands.
    assert _claimed_paths("[d](future.md) (planned)", "docs/adr/x.md") == []
    assert _claimed_paths("[d](future.md)", "docs/adr/x.md") == [
        (1, "docs/adr/future.md")
    ]


def test_the_planned_marker_belongs_to_one_occurrence():
    """Codex on PR #29. Searching the whole line excuses every copy of a path
    as soon as one of them is marked, so an unqualified claim about today
    rides out on a neighbour's plan."""
    line = "[future](docs/future.md) (planned); [now](docs/future.md)"

    assert _claimed_paths(line) == [(1, "docs/future.md")], "only the second one"

    # Order does not rescue it either.
    assert _claimed_paths("[now](docs/future.md); [f](docs/future.md) (planned)") == [
        (1, "docs/future.md")
    ]


def test_a_link_may_carry_a_title():
    """Codex on PR #29. `[guide](docs/guide.md "Guide")` is ordinary CommonMark
    and yielded no candidate at all, so deleting its target left the guard
    green."""
    assert _claimed_paths('[guide](docs/gone.md "Guide")') == [(1, "docs/gone.md")]
    assert _claimed_paths("[guide](docs/gone.md 'Guide')") == [(1, "docs/gone.md")]
    assert _claimed_paths("[guide](docs/gone.md)") == [(1, "docs/gone.md")]


def test_a_query_string_is_not_part_of_the_filename():
    """Codex on PR #29, and this one fails in the dangerous direction: a valid
    `[raw](README.md?raw=1)` was checked as the literal string and reported
    broken, turning CI red on a document that is correct."""
    assert _claimed_paths("[raw](README.md?raw=1)") == [(1, "README.md")]
    assert _exists("README.md"), "so the link above is green, as it should be"
    assert _claimed_paths("[raw](docs/gone.md?raw=1)") == [(1, "docs/gone.md")]


def test_a_query_is_stripped_before_the_path_character_filter():
    """Codex on PR #29, on the fix above rather than on the original code.

    The query removal was added *after* the `%<>{}|*` filter, so a destination
    whose query carries one of those characters — `docs/gone.md?value=%2A`, a
    percent-escape, which is exactly what a query string is made of — was
    discarded as a placeholder before the stripping ever ran. Deleting its
    target left the guard green."""
    assert _claimed_paths("[raw](docs/gone.md?value=%2A)") == [(1, "docs/gone.md")]
    assert _claimed_paths("[raw](docs/gone.md?a=b*c)") == [(1, "docs/gone.md")]
    # The filter still does its job on the path half, where it belongs.
    assert _claimed_paths("[x](docs/*.md)") == []


def test_the_planned_marker_survives_a_link_title():
    """Codex on PR #29, on the two fixes above meeting each other.

    Titles made `[design](docs/future.md "Draft")` a candidate, and the marker
    is matched from the end of the *destination* — so `_is_planned` was handed
    ` "Draft") (planned)` and saw no marker. A roadmap that titles the link to
    the file it plans to add turned CI red until that file was created: a
    false red, and this is the escape hatch whose whole job is to prevent
    one."""
    assert _claimed_paths('[design](docs/future.md "Draft") (planned)') == []
    assert _claimed_paths("[design](docs/future.md 'Draft') (planned)") == []
    # Still a claim without the marker, title or no title.
    assert _claimed_paths('[design](docs/future.md "Draft")') == [
        (1, "docs/future.md")
    ]
    # And the reference-style spelling, which carries a title of its own.
    assert _claimed_paths('[ui]: docs/future.md "Draft" (planned)') == []
    # With its positive counterpart in the same test: without one, deleting
    # the title support from MARKDOWN_REFERENCE would stop the line parsing
    # at all and the assertion above would pass for the wrong reason.
    assert _claimed_paths('[ui]: docs/gone.md "Draft"') == [(1, "docs/gone.md")]


def test_a_link_title_is_read_as_one_quoted_run():
    """Mutation testing on PR #29, on the title-stepping fix itself: both
    details of the pattern that reads a title were load-bearing and neither
    was pinned, so a mutant that dropped either passed the whole file.

    The quotes have to be *the same* quote. A title may legally contain the
    other one — `"It's a draft"` — and a pattern that accepts any quote to
    close any other stops at the apostrophe, leaving ` a draft" (planned)`
    where the marker should be: a false red on a roadmap.

    And the run has to be the shortest one. A greedy body runs past the title
    to the last quote anywhere on the line, so a sentence that quotes
    something later swallows the marker along with it — and, the other way
    round, a stray quote *after* the marker pulls the match past a marker that
    was doing its job."""
    assert _claimed_paths("""[ui]: docs/future.md "It's a draft" (planned)""") == []
    assert _claimed_paths('[d](docs/future.md "Draft") (planned) and "x"') == []
    # The shortest run, not the longest: here the marker sits inside what a
    # greedy read would call the title, and the claim stands.
    assert _claimed_paths("[d](docs/future.md 'Draft') ' (planned)") == [
        (1, "docs/future.md")
    ]


def test_a_link_is_normalized_wherever_the_dots_sit():
    """`..` is a path segment and not a prefix, so a destination that climbs
    in the middle resolves like any other."""
    assert _claimed_paths("[d](docs/../00_README.md)") == [(1, "00_README.md")]
    assert _claimed_paths("[d](../docs/../00_README.md)", "docs/x.md") == [
        (1, "00_README.md")
    ]


def test_a_link_to_a_directory_is_not_a_claim_about_a_file():
    """Internal review on PR #29, on two of the fixes meeting each other.

    Root-anchoring and dropping the extension requirement together turned
    `[home](/)` and `[here](./)` — "the repository root" and "where I am",
    both ordinary links — into a claim on `.`, which names no file and was
    duly reported missing. A false red, on the most innocuous link there
    is."""
    assert _claimed_paths("[home](/)") == []
    assert _claimed_paths("[here](./)") == []
    assert _claimed_paths("[home](/)", "docs/process.md") == []
    # A directory that is not the root still names something checkable.
    assert _claimed_paths("[d](../scripts/)", "docs/x.md") == [(1, "scripts")]


def test_the_planned_marker_reaches_through_angle_brackets():
    """Internal review on PR #29. CommonMark lets a reference definition wrap
    its destination in `<…>`, and the marker is matched from the end of the
    destination — so the closing `>` sat between path and marker exactly as a
    closing bracket does in the inline spelling, and the escape read as a
    no-op."""
    assert _claimed_paths("[ui]: <docs/future.md> (planned)") == []
    assert _claimed_paths("[ui]: <docs/gone.md>") == [(1, "docs/gone.md")]


def test_a_link_title_may_contain_the_other_delimiters():
    """Codex on PR #29, on the title support itself. CommonMark gives a title
    three delimiter pairs, and each may carry the other two — `"It's gone"` is
    ordinary English. The first attempt excluded both quote characters from
    every title whatever its delimiter, so those links produced no candidate
    at all and their targets could be deleted with the guard green."""
    assert _claimed_paths("""[g](docs/gone.md "It's gone")""") == [
        (1, "docs/gone.md")
    ]
    assert _claimed_paths("""[g](docs/gone.md 'A "Guide"')""") == [(1, "docs/gone.md")]
    assert _claimed_paths("[g](docs/gone.md (Guide))") == [(1, "docs/gone.md")]
    # The destination still ends where the title begins, not inside it.
    assert _claimed_paths("""[g](docs/gone.md "docs/other.md")""") == [
        (1, "docs/gone.md")
    ]


def test_the_planned_marker_survives_a_parenthesised_title():
    """Codex on PR #29, on the parenthesised-title support added one iteration
    earlier. The link parsed, but the marker is matched from the end of the
    destination and the skipper knew only quoted titles, so `_is_planned` saw
    ` (Draft)) (planned)` and required a file the roadmap had said it planned
    to add. The marker itself is parenthesised too, which is why the skipper
    has to refuse that one form explicitly — stepping over it would excuse
    nothing and discard the escape instead."""
    assert _claimed_paths("[d](docs/future.md (Draft)) (planned)") == []
    assert _claimed_paths("[d](docs/future.md (Draft))") == [(1, "docs/future.md")]
    # The marker is not a title: stepping over it would leave nothing to find.
    assert _claimed_paths("[ui]: docs/future.md (planned)") == []


def test_a_link_shown_inside_a_code_span_is_not_a_link():
    """Codex on PR #29. A code span *shows* Markdown rather than writing it,
    and the link scan ran over the raw line, so a document illustrating the
    `(planned)` escape with a whole example link made a claim it never made.
    A false red, and pointed at exactly the documents that explain this file.

    The span is blanked rather than removed, so offsets — and with them the
    marker's position — are unchanged for everything else on the line."""
    assert _claimed_paths("Use `[guide](docs/future.md)` as an example") == []
    assert _claimed_paths("`[ui]: docs/future.md` is the other spelling") == []
    # A real link on the same line as an illustrated one still counts, and
    # still at its own position.
    assert _claimed_paths("`[x](docs/a.md)` and [y](docs/gone.md)") == [
        (1, "docs/gone.md")
    ]
    assert _claimed_paths("`[x](docs/a.md)` and [y](docs/future.md) (planned)") == []


def test_a_fragment_is_not_part_of_the_filename():
    """Codex on PR #29, the same defect as the query string and in the same
    place: a fragment stayed attached until `_exists`, long after the
    placeholder filter had seen its percent-escapes. `docs/gone.md#name%20with%20spaces`
    is a valid link to a heading, and it was discarded whole."""
    assert _claimed_paths("[s](docs/gone.md#name%20with%20spaces)") == [
        (1, "docs/gone.md")
    ]
    assert _claimed_paths("[s](docs/gone.md#heading)") == [(1, "docs/gone.md")]
    assert _claimed_paths("[s](docs/gone.md?raw=1#heading)") == [(1, "docs/gone.md")]


def test_an_info_string_does_not_close_a_fence():
    """Codex on PR #29, on the fence work itself — and the third time this one
    block has produced the same class of miss. ```` ```python ```` is an
    *opening* fence's info string; a line shaped like one inside a block is
    content, and closing on it hands everything after it to the prose reader,
    which reads no bare paths at all."""
    fenced = "```\ncore/a.py\n```python\ncore/b.py\n```"
    assert _claimed_paths(fenced) == [(2, "core/a.py"), (4, "core/b.py")]
    # An info string on the opener is still an opener.
    assert _claimed_paths("```python\ncore/gone.py\n```") == [(2, "core/gone.py")]


def test_a_longer_fence_holds_a_shorter_one():
    """Codex on PR #29, on the fence fix itself. A four-backtick block exists
    precisely so a three-backtick line may sit inside it, and recording only
    three characters made that inner line close the block — so every path
    after it in the same block went unread, which is the miss the fence work
    was undertaken to remove."""
    assert _claimed_paths("````\n```\ncore/gone.py\n```\n````") == [
        (3, "core/gone.py")
    ]
    # And the closing run may be longer than the opener, never shorter.
    assert _claimed_paths("```\ncore/gone.py\n`````\nui/after.py") == [
        (2, "core/gone.py"),
    ]


def test_a_fence_may_be_indented():
    """Mutation testing on PR #29, on ground the tilde fix walked over: a
    fence inside a list item is indented, which is ordinary CommonMark, and
    reading the marker only at column zero leaves the block's paths unread —
    the same miss the tilde spelling had, one level in."""
    assert _claimed_paths("- item\n  ```\n  core/gone.py\n  ```") == [
        (3, "core/gone.py")
    ]
    assert _claimed_paths("- item\n  ~~~\n  core/gone.py\n  ~~~") == [
        (3, "core/gone.py")
    ]


def test_an_extensionless_root_link_is_still_a_claim():
    """Codex on PR #29, on the root-link fix rather than on the original code.

    Root destinations became claims, but the slash-less branch still asked for
    a file extension, and `[MIT License](LICENSE)` has none. That spelling is
    in `README.md`, `README.ru.md` and `CONTRIBUTING.md` today; deleting or
    renaming `LICENSE` would have broken all three with the guard green.

    The extension rule is about *backticked* tokens, where `core.pipeline.run`
    and `README.md` are told apart by nothing else. A link destination is a
    path by construction and needs no such tiebreak — the same reason the
    shape rule already skips it."""
    assert _claimed_paths("[MIT License](LICENSE)") == [(1, "LICENSE")]
    assert _exists("LICENSE"), "so the link above is green, as it should be"
    assert _claimed_paths("[gone](NO_SUCH_FILE)") == [(1, "NO_SUCH_FILE")]
    # A backticked bare word is still not a path: that is the naming-policy
    # card, 152 of them, and this fix must not drag it in.
    assert _claimed_paths("run `pytest` first") == []
    # It reaches the same file named from a nested document, which is where
    # all but one of the live documents would have to name it.
    assert _claimed_paths("[lic](../LICENSE)", "docs/x.md") == [(1, "LICENSE")]
    assert _claimed_paths("[a](../00_README.md)", "docs/x.md") == [(1, "00_README.md")]


def test_a_protocol_relative_url_is_not_a_repository_path():
    """Codex on PR #29. `[mirror](//example.com/docs/file.md)` is an external
    URL that borrows the page's scheme, so it carries no colon for the `:`
    test to catch and was normalized into a repository path nobody could ever
    have: a false red on a document that is correct."""
    assert _claimed_paths("[mirror](//example.com/docs/file.md)") == []
    assert _claimed_paths("[mirror]: //example.com/docs/file.md") == []
    # A single leading slash lands outside the checkout too, and reading it as
    # a repository path was worse than dropping it: the root `README.md` would
    # vouch for a link that points at `github.com/README.md`.
    assert _claimed_paths("[a](/README.md)") == []


def test_a_tilde_fence_is_a_fence_too():
    """Codex on PR #29. `~~~` is the other CommonMark fence, and it exists
    precisely for blocks that contain backticks — a tree diagram of a
    documentation folder is a plausible one. Tracking only ``` left every path
    in such a block unread while the guard claimed to cover fenced diagrams."""
    assert _claimed_paths("~~~\ncore/gone.py\n~~~") == [(2, "core/gone.py")]
    # A tilde fence closes a tilde fence; a backtick line inside it is content.
    fenced = "~~~\ncore/gone.py\n```\nui/also_gone.py\n~~~\nand `ui/third.py`"
    assert _claimed_paths(fenced) == [
        (2, "core/gone.py"),
        (4, "ui/also_gone.py"),
        (6, "ui/third.py"),
    ]


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
    # Climbing out of the tree is nobody's path — but "out of the tree" is
    # decided by where the climb lands, not by how it is spelled. GitHub's
    # `../../releases` idiom escapes from a *root* document, which is the only
    # place it is written and the only place it works: from two directories
    # down the same spelling lands back inside, on `releases`, and it is then
    # an ordinary broken link that GitHub renders as one too. An earlier
    # reading of this case invented a rule to excuse it at any depth, and that
    # rule cost `[lic](../LICENSE)` — the same file this guard had just been
    # taught to check — from every nested document in the tree.
    assert _claimed_paths("[rel](../../releases)", "README.md") == []
    assert _claimed_paths("[rel](../../releases)", "docs/adr/x.md") == [
        (1, "releases")
    ]
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
def test_a_document_is_selected_whatever_the_case_of_its_extension(
    tmp_path, monkeypatch
):
    """The document set was filtered by `name.endswith(".md")`, so a single
    capital let a whole file out of the guard.

    Nothing in this tree spells it that way today — 48 tracked `.md` files,
    none with a capital in the extension — so this is prevention rather than
    rot, and it is cheap enough to be worth having: the failure is silent, and
    the symptom is a document that is never checked rather than one that fails.
    `.markdown` is folded in for the same reason, being the other spelling
    GitHub renders.
    """
    _init_repository(tmp_path)
    (tmp_path / "GUIDE.MD").write_text("see `core/gone.py`\n", encoding="utf-8")
    (tmp_path / "NOTE.Markdown").write_text("see `core/gone.py`\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("see `core/gone.py`\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "GUIDE.MD", "NOTE.Markdown", "notes.txt"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(sys.modules[_exists.__module__], "PROJECT_ROOT", tmp_path)

    documents = _markdown_documents()

    assert "GUIDE.MD" in documents
    assert "NOTE.Markdown" in documents
    assert "notes.txt" not in documents, "the fold is about case, not about scope"
    assert "GUIDE.MD" in _live_documents()


@needs_git
def test_a_link_to_a_root_file_is_checked_even_without_a_slash(tmp_path, monkeypatch):
    """Codex on PR #29. The slashed-only boundary keeps *backticked bare
    names* out of scope — a naming policy, filed as its own card. A link is
    not that case: `[TASKS.md](TASKS.md)` says which file it means, and
    dropping it let a rename of `TASKS.md` break that link in `README.md`,
    `CONTRIBUTING.md` and `TASKS.md` itself with the guard green.

    Driven through :func:`_broken_paths_in` against a real repository rather
    than through the extractor, because the boundary being tested lives in
    that function: a first version of this test re-applied the filter in its
    own assertion and stayed green when the defect was restored by mutation.
    """
    _init_repository(tmp_path)
    (tmp_path / "README.md").write_text(
        "see [roadmap](TASKS.md) and `ci.yml`\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True
    )
    monkeypatch.setattr(sys.modules[_exists.__module__], "PROJECT_ROOT", tmp_path)

    assert _broken_paths_in("README.md") == ["README.md:1 -> TASKS.md"], (
        "the link names a root file that is not there; `ci.yml` is a bare "
        "backticked name and stays out of scope"
    )


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


def test_a_destination_may_carry_the_characters_code_is_filtered_on():
    """Codex on PR #29. The quote/paren filter is aimed at code caught in a
    fence, and a link destination is delimited by its own brackets — applying
    it there drops a legal filename instead, and a link to a missing
    `docs/ui_(draft).md` would report nothing at all.

    The regex has to reach the real closing bracket first: `[^)\\s]+` hands
    back `docs/ui_(draft`, which is not a path anyone wrote either."""
    assert _claimed_paths("[design](docs/ui_(draft).md)") == [
        (1, "docs/ui_(draft).md")
    ]
    assert _claimed_paths("[q](docs/it's.md)") == [(1, "docs/it's.md")]
    # Still a link, still checked, and still absent from the tree.
    assert not _exists("docs/ui_(draft).md")


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


def test_a_windows_spelling_is_the_same_claim_as_its_posix_one():
    """`scripts\\gone.py` and `scripts/gone.py` name one file, and only the
    second was read.

    The instructions this tree ships are dual-platform, so the Windows half of
    every pair went unchecked: `tests/fixtures/e2e_p2/README.md` tells the
    reader to run `scripts\\gen_fixtures_noprint.py` on two lines, and neither
    produced a claim. Measured on `16e3bcf`: 20 lines across the 25 live
    documents carry a backslash; 4 of those are Markdown escapes and 1 is a
    shell line continued onto the next row, leaving **15 that spell a path**.
    Exactly 2 of the 15 name a file of this repository.

    The other 13 were already silent, and by two rules rather than one: 8 are
    `venv\\Scripts\\…` or the Obsidian vault the `skill/` prompts describe,
    excused by their first segment, while 5 are absolute paths into somebody
    else's disk (`C:\\…`, `D:\\…`) and die one rule earlier, on the `:` that
    makes a token a URL. Neither `C:` nor `D:` is a head in
    `NOT_REPOSITORY_PATHS`, so saying all 13 are "excused by their first
    segment" would be exactly the unchecked sentence this module exists to
    catch.

    The separator is normalised on the *line*, before the line is split into
    tokens, and that is not a detail of where the call sits. Inside a fence a
    token earns its candidacy by carrying a slash at all, so a backslashed
    path is dropped before any rule about filenames is consulted — which is
    why the guard was silent rather than wrong here.
    """
    fence = "```bash\nvenv\\Scripts\\python scripts\\gone.py\n```"

    assert _claimed_paths(fence) == [(2, "scripts/gone.py")]
    assert _claimed_paths("run `scripts\\gone.py`") == [(1, "scripts/gone.py")]


def test_a_line_continuation_is_not_a_path():
    """A shell line broken across two rows ends in a lone backslash, which
    normalisation turns into a lone slash — `CONTRIBUTING.md:115` is exactly
    this, and the token it donates is `/`.

    It would not have been reported: `_exists` strips a trailing slash and
    answers `True` for the empty string that is left, so the claim passes for
    the wrong reason and inflates every count built on the claim list. A
    separator with nothing on either side of it is not a path anyone wrote.

    The continuation *creates* such a token; it is not where the existing
    ones came from, and the difference is worth keeping straight. Eleven bare
    `/` claims were already in the list on `16e3bcf`, every one of them an
    "A or B" written with spaces — `faster-whisper / sherpa-onnx` in a README
    diagram, `Агата / Адет` in a `skill/` prompt. Before this change a
    backslash was not normalised at all, so no continuation could have
    produced one. This guard removes eleven that predate it, and one that
    arrives with it: `CONTRIBUTING.md:115`.
    """
    fence = "```bash\ncore/run.py --flag \\\n```"

    assert _claimed_paths(fence) == [(2, "core/run.py")]
    assert _claimed_paths("```\n//\n```") == []


def test_an_uppercase_extension_still_names_a_file():
    """`FILE_SUFFIXES` is a vocabulary of file *types*, and a type is not
    spelled differently for being shouted. The comparison was case-sensitive,
    so `core/GONE.PY` read as prose with a slash in it and `README.MD` as a
    dotted symbol; both went unchecked.

    What is folded is the classification, not the lookup: `_exists` stays
    exact, because this tree is read on Linux where `README.MD` and
    `README.md` are two different files and vouching for one with the other is
    the rot this file exists to catch.
    """
    assert _is_path_shaped("core/GONE.PY")
    assert _claimed_paths("see `core/GONE.PY`") == [(1, "core/GONE.PY")]
    assert _claimed_paths("see `README.MD`") == [(1, "README.MD")]
    assert not _exists("README.MD"), "the tree carries README.md, a different name"


def test_a_link_to_a_markdown_document_is_recognised_as_one():
    """The two halves of "what counts as Markdown" have to move together.

    `_markdown_documents` reads a `.markdown` file as a document, so
    `FILE_SUFFIXES` has to recognise a path naming one — a vocabulary that
    guards a file while refusing to see the reference pointing at it is an
    exception nobody wrote down, and it is the exact shape of rot this module
    exists to catch. A Markdown link is not the case in question: a
    destination skips the shape rule by construction and is a claim either
    way. What is at stake is the backticked and the fenced spelling.

    Nothing in this tree is spelled that way today, which is why it needs a
    test rather than a document to hold it: drop `".markdown"` from the set
    and the document half stays green while every backticked or fenced
    reference to such a file quietly stops being a claim. Mutation found this
    uncovered, and nothing else in the file reddens for it.

    The assertions go through a token carrying a directory, and that is not
    arbitrary: `FILE_TOKEN` allows at most six characters of extension, so a
    bare `notes.markdown` is refused before the vocabulary is reached and
    reads as green with the entry and without it.
    """
    assert _is_path_shaped("docs/notes.markdown")
    assert _claimed_paths("see `docs/notes.markdown`") == [(1, "docs/notes.markdown")]
    assert _claimed_paths("```\ndocs/notes.markdown\n```") == [
        (2, "docs/notes.markdown")
    ]
    assert _claimed_paths("see `notes.markdown`") == [], (
        "a bare name never reaches the vocabulary: FILE_TOKEN stops at six"
    )


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
