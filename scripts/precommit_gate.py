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

They run against the **index**, and — whenever the working tree holds
anything the index does not — against the working tree as well.

The index is what ``git commit`` records, so it is the tree a green result
has to be about. ``git checkout-index -a --prefix=<tmp>/`` materialises
exactly that content into a throwaway directory: it reads the index, touches
neither the working tree nor the stash, and the checks are pointed at the
copy.

The working tree is the other half, and it is not optional. A PreToolUse hook
fires before the whole command line, so ``git add x.py && git commit`` — the
form this project's own process prescribes — reaches the gate with x.py still
unstaged, and the content that gets committed is the working-tree one.
``git commit -a``, ``--only`` and ``-p`` move the index after the hook has
run in the same way. Telling those cases apart means parsing the command
line, which is exactly what this gate no longer does; checking both trees
covers them without knowing which one is happening, because every file the
commit can draw from comes from one tree or the other.

That parse is gone on purpose. Five rounds of review found about two dozen
real defects in it, three of them introduced by its own fixes: ``git`` and
``sh`` have more syntax than a hook can model, and every misreading of the
model was a silent pass. Checking a tree needs no model.

The cost is a second run whenever the tree is dirty, and a refusal over
something broken in the working tree that the commit would not have carried.
Both are the deliberate direction: a needless refusal is visible and costs
one command to undo, while a silent pass is the exact failure the gate exists
to prevent.

A command line with no ``commit`` in it is left alone entirely, so that a
hook registered for every Bash call does not answer ``git status`` with a
full test run. The word test is deliberately cruder than a parse: standing
aside is the one outcome the gate cannot recover from, so it takes more than
a parser's say-so.

On Linux the fast suite needs the system Qt libraries listed in
CONTRIBUTING.md; without them pytest cannot start and the gate denies every
commit.

On success the gate is not silent: it hands back the two questions that green
tests do not answer, plus anything that weakens the guarantee it just gave.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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

#: The two trees a commit can draw its content from, named the same way in
#: everything the gate prints.
INDEX = "снимок индекса"
WORKTREE = "рабочее дерево"

#: How many paths the note names before it stops. A clone with build output
#: in it has hundreds, and a wall of them gets read as noise — which is the
#: one thing this list must not become.
MAX_LISTED = 20


class Check(NamedTuple):
    """One machine check.

    ``module`` is carried separately so that "this tool is not installed" can
    be told apart from "this tool ran and the code it checked has a broken
    import" — see :func:`_is_module_missing`.

    ``empty_code`` is the exit status the tool uses for "there was nothing
    here to check", or ``None`` when it has no such status. pytest exits 5 on
    an empty collection, which a snapshot of an empty index produces; that is
    an absent check, not a failing one, and denying the commit over it would
    be a refusal the developer cannot act on.
    """

    label: str
    module: str
    argv: list[str]
    empty_code: int | None


CHECKS: list[Check] = [
    Check(
        "ruff F821 (undefined names)",
        "ruff",
        [PYTHON, "-m", "ruff", "check", "--select", "F821", "--quiet", "."],
        None,
    ),
    Check(
        "pytest (fast suite)",
        "pytest",
        [PYTHON, "-m", "pytest", "-q", "-m", "not slow and not requires_asr"],
        5,
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


def _snapshot_index(destination: Path) -> bool:
    """Materialise the index into *destination*. False if it could not be.

    ``git checkout-index -a --prefix=<dir>/`` writes every file the index
    holds, creating the directories it needs, and reads nothing from the
    working tree. The trailing separator is what makes ``--prefix`` a
    directory rather than a filename prefix, and the path is given in posix
    form because git wants forward slashes on Windows too.

    The destination is created here rather than left to git, because git
    creates only the directories it has files to put in: an empty index
    leaves none at all, and a check pointed at a path that does not exist
    comes back as FileNotFoundError — which this gate reads as "the tool is
    not installed" and forgives. An unchecked commit must not be able to
    arrive dressed as a missing tool.

    Every failure here — an unwritable directory as much as a refusing git —
    comes back as False rather than as an exception. An exception escapes the
    hook, which then prints no decision at all, and standing aside silently
    is the one outcome the gate cannot recover from.
    """
    prefix = f"{destination.as_posix().rstrip('/')}/"
    try:
        destination.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "checkout-index", "-a", f"--prefix={prefix}"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _outside_the_index() -> list[str]:
    """Working-tree content the index snapshot does not carry.

    Unstaged edits to tracked files and untracked files alike: neither is in
    the index, so neither is in the snapshot. A file that is both staged and
    further edited belongs here too — the snapshot holds its staged half, and
    the edit on top of it exists only in the tree.

    Emptiness here is what decides whether the working tree needs checking at
    all: nothing outside the index means the two trees agree about every file
    the commit could draw from, and one run covers both.
    """
    modified = set(_git("diff", "--name-only"))
    untracked = set(_git("ls-files", "--others", "--exclude-standard"))
    return sorted(modified | untracked)


def _listing(paths: list[str]) -> str:
    """*paths* as a bulleted list, cut off before it turns into wallpaper."""
    shown = [f"  - {path}" for path in paths[:MAX_LISTED]]
    remainder = len(paths) - MAX_LISTED
    if remainder > 0:
        shown.append(f"  … и ещё {remainder}")
    return "\n".join(shown)


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


def _run_checks(workdir: Path, tree: str) -> tuple[str | None, list[str]]:
    """Run every check in *workdir*, naming it *tree* in what it reports.

    Returns ``(denial reason or None, checks that never ran)``.
    """
    skipped: list[str] = []
    for check in CHECKS:
        try:
            result = subprocess.run(
                check.argv,
                cwd=workdir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except FileNotFoundError:
            # No interpreter at all — not a reason to block a commit, or a
            # fresh clone becomes uncommittable.
            skipped.append(f"{check.label}: интерпретатор не найден")
            continue
        except subprocess.TimeoutExpired:
            return (
                f"{check.label}: не уложился в 180 с ({tree}). "
                "Запусти вручную и посмотри.",
                skipped,
            )

        if result.returncode == 0:
            continue

        output = (result.stdout + result.stderr).strip()
        if _is_module_missing(output, check.module):
            skipped.append(f"{check.label}: не установлен")
            continue
        if check.empty_code is not None and result.returncode == check.empty_code:
            skipped.append(f"{check.label}: проверять нечего ({tree})")
            continue

        tail = "\n".join(output.splitlines()[-25:])
        return (
            f"Коммит остановлен: {check.label} не прошёл ({tree}).\n\n{tail}\n\n"
            "Почини и повтори.",
            skipped,
        )

    return None, skipped


def _judge(snapshot: Path | None, outside: list[str]) -> int:
    """Decide on the trees that are available, and say which they were."""
    trees: list[tuple[str, Path]] = []
    degraded = ""
    if snapshot is not None:
        trees.append((INDEX, snapshot))
    else:
        degraded = (
            "\n\nСнимок индекса собрать не удалось — проверено только "
            f"{WORKTREE}. Это другой код, чем тот, который запишет коммит."
        )
    if outside or not trees:
        trees.append((WORKTREE, PROJECT_ROOT))

    reason: str | None = None
    skipped: list[str] = []
    for tree, workdir in trees:
        reason, missing = _run_checks(workdir, tree)
        skipped += [item for item in missing if item not in skipped]
        if reason is not None:
            break

    if reason is not None:
        _deny(reason + degraded)
        return 0

    note = REMINDERS + degraded
    note += "\n\nПроверено: " + ", ".join(tree for tree, _ in trees) + "."
    if skipped:
        note += f"\n\nНе проверено (инструмента нет):\n{_listing(skipped)}"
    if outside:
        note += (
            "\n\nВ рабочем дереве есть то, чего нет в индексе:\n"
            f"{_listing(outside)}\n"
            "Обычный коммит их не запишет, но хук срабатывает до всей "
            "командной строки: git add в той же строке, а также git commit "
            "-a, --only и -p проиндексируют их уже после проверки. Поэтому "
            "дерево проверено наравне со снимком."
        )
    _allow_with_note(note)
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — a hook must never die on its input
        payload = {}

    command = str((payload.get("tool_input") or {}).get("command") or "")

    if "commit" not in command:
        # Not a commit at all. The hook may be registered for every Bash
        # call, and running the suite on `git status` would deny the very
        # commands someone runs to diagnose a failing test.
        return 0

    outside = _outside_the_index()
    try:
        with tempfile.TemporaryDirectory(prefix="precommit-gate-") as workspace:
            snapshot = Path(workspace) / "index"
            return _judge(snapshot if _snapshot_index(snapshot) else None, outside)
    except OSError:
        # Not even a temporary directory: a full disk, an unwritable TMPDIR.
        # Dying here would print no decision at all and leave the commit
        # unexamined, so the working tree has to carry the check alone.
        return _judge(None, outside)


if __name__ == "__main__":
    raise SystemExit(main())
