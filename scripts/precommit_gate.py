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
all. Where the command cannot be read confidently, the gate withholds the
index-derived observations instead of guessing at them.

On Linux the fast suite needs the system Qt libraries listed in
CONTRIBUTING.md; without them pytest cannot start and the gate denies every
commit.

On success the gate is not silent: it hands back the two questions that green
tests do not answer, plus anything that weakens the guarantee it just gave.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

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


#: Shell operators that end one command and begin the next.
_SHELL_SEPARATORS = frozenset({"&&", "||", ";", "|", "&"})

#: ``git commit`` options that consume the following argument, so that
#: argument is a value and not a pathspec.
_COMMIT_VALUE_FLAGS = frozenset(
    {
        "-m", "--message", "-F", "--file", "-C", "--reuse-message",
        "-c", "--reedit-message", "--author", "--date", "--cleanup",
        "-t", "--template", "--trailer", "--squash", "--fixup",
    }
)

#: The same options in short-cluster form (``-am "msg"`` ends in ``m``).
_COMMIT_VALUE_LETTERS = "mFCct"

#: ``git add`` options that stage more than the paths spelled out next to
#: them, so the resulting index cannot be predicted path by path.
_ADD_STAGES_EVERYTHING = frozenset({"-A", "--all", "-u", "--update", "--pathspec-from-file"})

#: A pathspec containing any of these is a pattern, not a plain path.
_GLOB_CHARS = "*?["


def _argv_after(command: str, *prefix: str) -> list[str] | None:
    """Arguments of the first ``prefix`` invocation in a shell command line.

    ``None`` when the command does not contain that invocation, or cannot be
    tokenised at all.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    width = len(prefix)
    for start in range(len(tokens) - width + 1):
        if tuple(tokens[start : start + width]) != prefix:
            continue
        argv: list[str] = []
        for token in tokens[start + width :]:
            if token in _SHELL_SEPARATORS:
                break
            argv.append(token)
        return argv
    return None


def _commit_selects_paths(command: str) -> bool:
    """True when ``git commit`` names the paths it is going to record.

    ``git commit -- a.py``, ``git commit --only a.py`` and the bare
    ``git commit a.py`` all commit *those paths* and leave the rest of the
    index untouched (``git commit -h``, ``--only``). Nothing the gate reads
    off the index describes such a commit, so it reports nothing about it.
    """
    argv = _argv_after(command, "git", "commit")
    if argv is None:
        return False
    expecting_value = False
    for token in argv:
        if expecting_value:
            expecting_value = False
            continue
        if token in ("--", "--only", "-o"):
            return True
        if token.startswith("--"):
            expecting_value = token in _COMMIT_VALUE_FLAGS
            continue
        if token.startswith("-") and len(token) > 1:
            if "o" in token[1:]:
                return True
            expecting_value = token[-1] in _COMMIT_VALUE_LETTERS
            continue
        return True  # a bare argument is a pathspec
    return False


def _commit_stages_everything(command: str) -> bool:
    """True for ``git commit -a`` — it stages every tracked modification."""
    argv = _argv_after(command, "git", "commit")
    if argv is None:
        return False
    for token in argv:
        if token == "--":
            break
        if token == "--all":
            return True
        if not token.startswith("--") and token.startswith("-") and "a" in token[1:]:
            return True
    return False


def _restaged_paths(command: str) -> set[str] | None:
    """Paths a ``git add`` in *command* is about to move into the index.

    A PreToolUse hook fires before the command runs, so for
    ``git add … && git commit`` the index the gate can see is not yet the
    index that will be committed — but only for the paths that ``git add``
    actually names. Everything else keeps whatever split state it already has.

    An empty set means the command stages nothing, so the index is already
    final. ``None`` means the whole index is about to be rewritten (``git add
    .``, ``-A``, a glob, ``git commit -a``) or the command cannot be read
    confidently — in both cases the gate withholds its index-derived
    observations rather than inventing them.
    """
    if _commit_stages_everything(command):
        return None
    argv = _argv_after(command, "git", "add")
    if argv is None:
        return set()
    paths: set[str] = set()
    for token in argv:
        if token in _ADD_STAGES_EVERYTHING:
            return None
        if token.startswith("-"):
            continue
        if token == "." or token.startswith(":") or any(c in token for c in _GLOB_CHARS):
            return None
        paths.add(token.rstrip("/"))
    return paths or None


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
    if _commit_selects_paths(command):
        conflicted: list[str] = []
        dirty: list[str] = []
    else:
        restaged = _restaged_paths(command)
        if restaged is None:
            conflicted, dirty = [], []
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
