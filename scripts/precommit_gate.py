"""Pre-commit gate: refuse a commit that the machine can already tell is broken.

Wired as a Claude Code PreToolUse hook on ``git commit`` (see
``.claude/settings.json``). Reads the hook payload on stdin, writes a hook
decision as JSON on stdout.

Two checks, in the order that fails fastest:

1. ``ruff --select F821`` — undefined names. Not style policing: a name that
   does not exist raises NameError at runtime, and a broad ``except`` around
   it turns that into silently missing output.

2. The fast test suite. It runs in a few seconds, so "did you run the tests"
   does not need to be something anyone remembers.

Both run against the working tree, while ``git commit`` records the index.
The gate therefore refuses to run at all when a file is staged *and* has
further unstaged edits, because in that case a green result would describe
code that is not the code being committed.

Working out *which* file that applies to means reading the command the hook
fired on: ``git add b.py && git commit`` is about to make b.py whole but
leaves any other half-staged file exactly as broken, and
``git commit -- a.py`` records the paths it names rather than the index at
all. That reading is a shell parse, not a token scan — a command block is
several commands, and ``;``, a newline and a redirection all end one.

Order matters too. Only a ``git add`` that runs before the commit settles
anything, and only when nothing between here and the commit can rewrite the
files being checked: the hook fires before the whole line, so a command that
writes ``a.py`` after ruff and pytest have read it leaves their result
describing code that no longer exists.

Where the command cannot be parsed the gate falls back to the index as it
stands, and so may refuse a commit it had no business refusing. That is the
deliberate direction: a needless refusal is visible and costs one command to
undo, while the opposite default costs a silent pass — the exact failure the
gate exists to prevent.

A command line with no ``git commit`` in it is left alone entirely, so that a
hook registered for every Bash call does not answer ``git status`` with a
full test run.

On Linux the fast suite needs the system Qt libraries listed in
CONTRIBUTING.md; without them pytest cannot start and the gate denies every
commit.

On success the gate is not silent: it hands back the two questions that green
tests do not answer, plus anything that weakens the guarantee it just gave.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: The interpreter that owns this project's dependencies. ``Scripts`` on
#: Windows, ``bin`` everywhere else. Falls back to whatever is running the
#: hook, so a fresh clone without a venv gets a useful error instead of a
#: confusing one.
_VENV_CANDIDATES = (
    PROJECT_ROOT / "venv" / "Scripts" / "python.exe",
    PROJECT_ROOT / "venv" / "bin" / "python",
)
PYTHON = next(
    (str(path) for path in _VENV_CANDIDATES if path.is_file()),
    sys.executable,
)

#: ``(label, module, argv)``. The module name is carried separately so that
#: "this tool is not installed" can be told apart from "this tool ran and the
#: code it checked has a broken import" — see :func:`_is_module_missing`.
CHECKS: list[tuple[str, str, list[str]]] = [
    (
        "ruff F821 (undefined names)",
        "ruff",
        [PYTHON, "-m", "ruff", "check", "--select", "F821", "--quiet", "."],
    ),
    (
        "pytest (fast suite)",
        "pytest",
        [PYTHON, "-m", "pytest", "-q", "-m", "not slow and not requires_asr"],
    ),
]

#: What the machine cannot check, asked at the moment it still matters.
REMINDERS = (
    "Проверки прошли. Их недостаточно — ответь себе на два вопроса, "
    "на которые зелёные тесты не отвечают:\n"
    "  1. Диф отревьюен? (агент reviewer, не самопроверка)\n"
    "  2. Фича доходит до пользователя? Назови точку входа, через "
    "которую она реально вызывается."
)


def _git(*args: str) -> list[str]:
    """Return the non-empty lines of a git command, or [] if git is unusable."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _staged_but_dirty() -> list[str]:
    """Files that are staged and carry further unstaged edits.

    For these the working tree and the index disagree about the very content
    being committed, so a check run against the working tree proves nothing
    about the commit.
    """
    staged = set(_git("diff", "--cached", "--name-only"))
    unstaged = set(_git("diff", "--name-only"))
    return sorted(staged & unstaged)


def _dirty_elsewhere() -> list[str]:
    """Working-tree content the checks see that the commit will not carry.

    Untracked files count. ``git diff`` never mentions them, but staged code
    can import a helper that exists only in the working tree: the checks pass
    against it and a clean checkout of the commit fails on the missing file.
    """
    staged = set(_git("diff", "--cached", "--name-only"))
    modified = set(_git("diff", "--name-only")) - staged
    untracked = set(_git("ls-files", "--others", "--exclude-standard"))
    return sorted(modified | untracked)


def _deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )


def _allow_with_note(note: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": note,
            }
        },
        sys.stdout,
    )


def _is_module_missing(output: str, module: str) -> bool:
    """True only when the interpreter could not start *module* itself.

    ``python -m <tool>`` starts the interpreter successfully and only then
    fails, so a missing tool arrives as a non-zero exit rather than as
    FileNotFoundError. The interpreter prints the name bare::

        /usr/bin/python3: No module named ruff

    A ``ModuleNotFoundError`` raised *inside* a check that did start quotes
    it instead (``No module named 'foo'``). The distinction is the whole
    guarantee: matching both would let staged code with a broken import be
    reported as "pytest is not installed", skipping the check that would
    have caught it and passing the commit.
    """
    bare = f"No module named {module}"
    for line in output.splitlines():
        _, separator, rest = line.rstrip().partition(bare)
        if not separator:
            continue
        # End of line, or the ``<module>.__main__`` form Python uses for a
        # package that is installed but has no entry point.
        if not rest or rest.startswith(".__main__"):
            return True
    return False


#: Shell operators that end one command and begin the next. Longest first —
#: ``&&`` must be recognised before ``&``. A newline is one of them: a command
#: block is several commands, not one long line.
_SHELL_SEPARATORS = ("&&", "||", ";", "|", "&", "\n")

#: Redirections, which belong to the shell and not to git's argument list.
_REDIRECTION = re.compile(r"^\d*(?:>>|>&|>|<<<|<<|<)")

#: ``git commit`` options that consume the following argument, so that
#: argument is a value and not a pathspec.
_COMMIT_VALUE_FLAGS = frozenset(
    {
        "-m", "--message", "-F", "--file", "-C", "--reuse-message",
        "-c", "--reedit-message", "--author", "--date", "--cleanup",
        "-t", "--template", "--trailer", "--squash", "--fixup",
    }
)

#: The same options in short-cluster form (``-am "msg"`` ends in ``m``). Such
#: a letter swallows the rest of the cluster, so ``-mdata`` is a message and
#: not the flags ``d``, ``a``, ``t``, ``a``.
_COMMIT_VALUE_LETTERS = "mFCct"

#: ``git add`` options after which the resulting index cannot be predicted
#: from the command line: the user picks hunks, or nothing is staged at all.
_ADD_UNCREDITABLE = frozenset(
    {"-p", "--patch", "-i", "--interactive", "-e", "--edit", "-n", "--dry-run",
     "--pathspec-from-file"}
)

#: Commands that may run before the commit without invalidating what the
#: checks just measured. ``git add`` is handled separately; anything outside
#: this set can rewrite the very files ruff and pytest were pointed at.
_INERT_BEFORE_COMMIT = frozenset(
    {"status", "diff", "log", "rev-parse", "branch", "fetch", "remote", "config"}
)

#: A pathspec containing any of these is a pattern, not a plain path.
_GLOB_CHARS = "*?["


class _Unreadable(Exception):
    """The command line could not be parsed, so nothing may be inferred from it."""


class _Plan(NamedTuple):
    """What a command line is about to do, as far as it can be read.

    ``inert`` is False when something other than ``git add`` runs before the
    commit: a redirection into a source file, a formatter, a script. The
    checks run *before* the whole line, so anything that rewrites files
    afterwards makes their result describe code that no longer exists.
    """

    inert: bool
    adds: list[list[str]]
    commits: list[list[str]]


def _split_segments(command: str) -> list[str] | None:
    """Split a shell command line into the simple commands it is made of.

    Quote-aware, because an operator inside quotes is text: the ``&&`` in
    ``git commit -m "a && b"`` separates nothing. ``None`` means the line
    could not be scanned — an unbalanced quote, a heredoc — and a
    half-understood command line must not be passed off as understood.
    """
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    position = 0
    while position < len(command):
        char = command[position]
        if quote is not None:
            current.append(char)
            if char == "\\" and quote == '"' and position + 1 < len(command):
                current.append(command[position + 1])
                position += 2
                continue
            if char == quote:
                quote = None
            position += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            position += 1
            continue
        if char == "\\" and position + 1 < len(command):
            # An escaped character, including the ``\`` + newline that
            # continues one command onto the next line.
            current.append(char)
            current.append(command[position + 1])
            position += 2
            continue
        separator = next(
            (sep for sep in _SHELL_SEPARATORS if command.startswith(sep, position)),
            None,
        )
        if separator is not None:
            segments.append("".join(current))
            current = []
            position += len(separator)
            continue
        current.append(char)
        position += 1
    if quote is not None:
        return None
    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]


def _dequote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return token[1:-1]
    return token


def _tokenise(segment: str) -> list[str] | None:
    """The words of one simple command, without its shell decorations."""
    # posix=False keeps backslashes intact, so a Windows pathspec such as
    # ``scripts\gate.py`` survives tokenising; the quotes it leaves on tokens
    # come off in _dequote. The default commenters are kept, so the tail of
    # ``git commit -m x  # note`` is a comment and not three pathspecs.
    lexer = shlex.shlex(segment, posix=False)
    lexer.whitespace_split = True
    try:
        raw = list(lexer)
    except ValueError:
        return None
    tokens: list[str] = []
    skip_next = False
    for token in raw:
        if skip_next:
            skip_next = False
            continue
        redirection = _REDIRECTION.match(token)
        if redirection:
            # ``2>&1`` carries its target; a bare ``>`` takes the next word.
            skip_next = redirection.end() == len(token)
            continue
        tokens.append(_dequote(token))
    return tokens


def _plan(command: str) -> _Plan:
    """Read a shell command line into the parts the gate reasons about.

    Order matters: only a ``git add`` that runs *before* the commit settles
    anything, and only if nothing between here and the commit can rewrite
    the files the checks are about to read.

    Raises :class:`_Unreadable` when the line cannot be scanned at all.
    """
    segments = _split_segments(command)
    if segments is None:
        raise _Unreadable
    adds: list[list[str]] = []
    commits: list[list[str]] = []
    inert = True
    for segment in segments:
        tokens = _tokenise(segment)
        if tokens is None:
            raise _Unreadable
        if not tokens:
            continue
        if commits:
            # Everything past the commit is somebody else's business.
            continue
        if tokens[0] == "cd":
            continue
        if tokens[0] != "git" or len(tokens) < 2:
            inert = False
            continue
        subcommand, argv = tokens[1], tokens[2:]
        if subcommand == "commit":
            commits.append(argv)
        elif subcommand == "add":
            adds.append(argv)
        elif subcommand not in _INERT_BEFORE_COMMIT:
            inert = False
    return _Plan(inert=inert, adds=adds, commits=commits)


def _normalise(pathspec: str) -> str:
    """A pathspec in the shape ``git diff --name-only`` reports paths."""
    path = pathspec.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.rstrip("/")


def _commit_selects_paths(argv: list[str]) -> bool:
    """True when ``git commit`` names the paths it is going to record.

    ``git commit -- a.py``, ``git commit --only a.py`` and the bare
    ``git commit a.py`` all commit *those paths* and leave the rest of the
    index untouched (``git commit -h``, ``--only``). Nothing the gate reads
    off the index describes such a commit, so it reports nothing about it.
    """
    expecting_value = False
    for token in argv:
        if expecting_value:
            expecting_value = False
            continue
        if token in ("--", "--only"):
            return True
        if token.startswith("--"):
            expecting_value = token in _COMMIT_VALUE_FLAGS
            continue
        if token.startswith("-") and len(token) > 1:
            expecting_value = _cluster_takes_next_word(token, stop_at="o")
            if expecting_value is None:
                return True
            continue
        return True  # a bare argument is a pathspec
    return False


def _cluster_takes_next_word(token: str, stop_at: str) -> bool | None:
    """Walk a short-option cluster such as ``-am``.

    ``None`` means *stop_at* was found before any value-taking letter.
    Otherwise True when the cluster ends on a letter that takes the next word
    as its value. Scanning stops at the first value-taking letter, because
    ``-mdata`` is the message ``data`` — not the flags ``d``, ``a``, ``t``.
    """
    for index, letter in enumerate(token[1:], start=1):
        if letter == stop_at:
            return None
        if letter in _COMMIT_VALUE_LETTERS:
            return index == len(token) - 1
    return False


def _commit_stages_everything(argv: list[str]) -> bool:
    """True for ``git commit -a`` — it stages every tracked modification."""
    for token in argv:
        if token == "--":
            break
        if token == "--all":
            return True
        if token.startswith("--"):
            continue
        if token.startswith("-") and len(token) > 1:
            if _cluster_takes_next_word(token, stop_at="a") is None:
                return True
    return False


def _add_scope(argv: list[str]) -> set[str] | None:
    """The pathspecs one ``git add`` will stage, or ``None`` for the lot.

    ``-A`` and ``-u`` widen *what kinds of change* are staged, not *where*:
    ``git add -u b.py`` still touches only b.py (``git add -h``:
    ``git add [<options>] [--] <pathspec>...``). So a pathspec, when given,
    is the scope regardless of the flags beside it.
    """
    paths: set[str] = set()
    skip_next = False
    after_separator = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token == "--":
            after_separator = True
            continue
        if not after_separator and token.startswith("-"):
            skip_next = token == "--chmod"
            continue
        if token == "." or token.startswith(":") or any(c in token for c in _GLOB_CHARS):
            return None
        paths.add(_normalise(token))
    # No pathspec at all: whatever the flags mean, they mean it everywhere.
    return paths or None


def _restaged_paths(plan: _Plan) -> set[str] | None:
    """Paths the command is about to move into the index before committing.

    A PreToolUse hook fires before the command runs, so for
    ``git add … && git commit`` the index the gate can see is not yet the
    index that will be committed — but only for the paths that ``git add``
    actually names. Everything else keeps whatever split state it already has.

    An empty set means nothing is settled in advance, so the index as it
    stands is what gets judged. ``None`` means the whole index is about to be
    rewritten — ``git add .``, ``git commit -a`` — and no per-path conclusion
    holds.
    """
    if any(_commit_stages_everything(argv) for argv in plan.commits):
        return None
    if not plan.inert:
        # Something between here and the commit can rewrite the files the
        # checks are about to read, so no staging may be credited in advance.
        return set()
    paths: set[str] = set()
    for argv in plan.adds:
        if any(token in _ADD_UNCREDITABLE for token in argv):
            # ``git add -p`` stages the hunks a human picks; the index it
            # leaves cannot be read off the command line.
            return set()
        scope = _add_scope(argv)
        if scope is None:
            return None
        paths |= scope
    return paths


def _covered_by(path: str, pathspecs: set[str]) -> bool:
    """True when *path* is one of *pathspecs* or sits inside one of them."""
    return any(path == spec or path.startswith(f"{spec}/") for spec in pathspecs)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — a hook must never die on its input
        payload = {}

    command = str((payload.get("tool_input") or {}).get("command") or "")

    # Reduce the gate's two index-derived observations to the files the
    # commit will actually contain. A path-selecting commit maps onto nothing
    # the index says; a ``git add`` in the same line settles the paths it
    # names and leaves every other half-staged file just as broken.
    #
    # When the command cannot be parsed the gate reports the index as it
    # stands. That can cost a needless refusal, which the developer sees and
    # can undo in one command — while the opposite default costs a silent
    # pass, which is the exact failure this gate exists to prevent.
    try:
        plan = _plan(command)
        if not plan.commits:
            # Not a commit at all. The hook may be registered for every Bash
            # call, and running the suite on `git status` would deny the very
            # commands someone runs to diagnose a failing test.
            return 0
        if any(_commit_selects_paths(argv) for argv in plan.commits):
            restaged: set[str] | None = None
            selects_paths = True
        else:
            restaged = _restaged_paths(plan)
            selects_paths = False
    except _Unreadable:
        restaged, selects_paths = set(), False

    if selects_paths or restaged is None:
        conflicted: list[str] = []
        dirty: list[str] = []
    else:
        conflicted = [p for p in _staged_but_dirty() if not _covered_by(p, restaged)]
        dirty = [p for p in _dirty_elsewhere() if not _covered_by(p, restaged)]

    if conflicted:
        listing = "\n".join(f"  - {path}" for path in conflicted)
        _deny(
            "Коммит остановлен: проиндексированы не все правки в этих "
            f"файлах.\n\n{listing}\n\n"
            "Проверки гоняются по рабочему дереву, а коммит записывает "
            "индекс — зелёный результат описывал бы не тот код, который "
            "уходит в коммит. Проиндексируй остаток (git add) или убери "
            "его (git stash --keep-index) и повтори."
        )
        return 0

    skipped: list[str] = []

    for label, module, check_argv in CHECKS:
        try:
            result = subprocess.run(
                check_argv,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except FileNotFoundError:
            # No interpreter at all — not a reason to block a commit, or a
            # fresh clone becomes uncommittable.
            skipped.append(f"{label}: интерпретатор не найден")
            continue
        except subprocess.TimeoutExpired:
            _deny(f"{label}: не уложился в 180 с. Запусти вручную и посмотри.")
            return 0

        if result.returncode == 0:
            continue

        output = (result.stdout + result.stderr).strip()
        if _is_module_missing(output, module):
            skipped.append(f"{label}: не установлен")
            continue

        tail = "\n".join(output.splitlines()[-25:])
        _deny(f"Коммит остановлен: {label} не прошёл.\n\n{tail}\n\nПочини и повтори.")
        return 0

    note = REMINDERS
    if skipped:
        listing = "\n".join(f"  - {item}" for item in skipped)
        note += f"\n\nНе проверено (инструмента нет):\n{listing}"
    if dirty:
        listing = "\n".join(f"  - {path}" for path in dirty)
        note += (
            "\n\nВ рабочем дереве есть правки и файлы вне индекса — тесты "
            f"гонялись вместе с ними, в коммит они не попадут:\n{listing}"
        )
    _allow_with_note(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
