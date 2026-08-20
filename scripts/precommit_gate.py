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
line, which is exactly what this gate no longer does, so it looks at both
trees instead: every file such a commit records comes from one of them, and
both have been read.

That is per file, and it is worth being exact about what it is not. A
path-limited commit records a *mixture* — the named path from the tree, the
rest from the index or from HEAD — and no run here materialises that
mixture. Each half was seen; their combination was not. Closing that would
mean reading the command line again, so the gate does not claim it.

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
import shutil
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
    be a refusal the developer cannot act on. It is only ever read for a tree
    that holds nothing at all — pytest exits 5 for a suite that collected
    nothing too, and a staged change to ``python_files`` can arrange exactly
    that, which is a check silenced rather than a check with nothing to do.

    ``on_index`` is appended when the check runs against the snapshot. The
    snapshot holds the index and nothing else, so a tool that skips
    gitignored paths there skips *tracked* files — the ones the commit is
    made of.
    """

    label: str
    module: str
    argv: list[str]
    empty_code: int | None
    on_index: tuple[str, ...] = ()


CHECKS: list[Check] = [
    Check(
        "ruff F821 (undefined names)",
        "ruff",
        [PYTHON, "-m", "ruff", "check", "--select", "F821", "--quiet", "."],
        None,
        # ruff honours .gitignore by default, which is right for the working
        # tree and wrong for the snapshot: a tracked file matched by an
        # ignore rule is still in the index, still in the commit, and would
        # otherwise never be looked at. ruff's own default excludes (venv,
        # build, node_modules…) are unaffected by this.
        on_index=("--no-respect-gitignore",),
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


def _git(*args: str) -> list[str] | None:
    """The non-empty lines of a git command, or None if git could not answer.

    None and ``[]`` must not be the same value here. "Nothing to report" is
    what lets the gate skip a whole run; "git timed out on a large
    repository" is not, and collapsing the two would drop that run silently.
    """
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
        return None
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def _snapshot_index(destination: Path) -> bool:
    """Materialise the index into *destination*. False if it could not be.

    ``git checkout-index -a --prefix=<dir>/`` writes the files the index
    holds, creating the directories it needs, and reads nothing from the
    working tree. "The files it holds" has one exception worth knowing: an
    unmerged path in the middle of a conflict is written by nothing and git
    still exits 0. That leaves the snapshot short of a file — but a
    conflicted path is always in ``git diff --name-only`` too, so the
    working-tree run happens and covers it. The trailing separator is what makes ``--prefix`` a
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
            [
                "git",
                "checkout-index",
                "-a",
                # A sparse checkout marks the paths it does not materialise
                # with skip-worktree, and ``-a`` alone honours that mark. But
                # those entries are still in the index, so they are still in
                # the commit: without this the snapshot is a subset of what
                # gets recorded, and the checks pass over the missing part.
                "--ignore-skip-worktree-bits",
                f"--prefix={prefix}",
            ],
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


def _outside_the_index() -> list[str] | None:
    """Working-tree content the index snapshot does not carry, or None.

    Unstaged edits to tracked files and untracked files alike: neither is in
    the index, so neither is in the snapshot. A file that is both staged and
    further edited belongs here too — the snapshot holds its staged half, and
    the edit on top of it exists only in the tree.

    Emptiness here is what decides whether the working tree needs checking at
    all: nothing outside the index means the two trees agree about every file
    the commit could draw from, and one run covers both. That is why "git
    could not tell me" has to be its own answer — read as emptiness it would
    cancel the second run without a word, and the bigger the repository the
    likelier git is to be the one that times out.
    """
    modified = _git("diff", "--name-only")
    untracked = _git("ls-files", "--others", "--exclude-standard")
    if modified is None or untracked is None:
        return None
    return sorted(set(modified) | set(untracked))


def _listing(paths: list[str]) -> str:
    """*paths* as a bulleted list, cut off before it turns into wallpaper."""
    shown = [f"  - {path}" for path in paths[:MAX_LISTED]]
    remainder = len(paths) - MAX_LISTED
    if remainder > 0:
        shown.append(f"  … и ещё {remainder}")
    return "\n".join(shown)


def _denial(reason: str) -> dict:
    return {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }


def _pass(note: str) -> dict:
    return {"hookEventName": "PreToolUse", "additionalContext": note}


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
    barren = not any(workdir.iterdir())
    for check in CHECKS:
        argv = list(check.argv)
        if tree == INDEX:
            argv += check.on_index
        try:
            result = subprocess.run(
                argv,
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
            if barren:
                skipped.append(f"{check.label}: проверять нечего ({tree})")
                continue
            # The tree has files and the tool still found nothing to do. That
            # is the check being silenced — a staged pytest.ini narrowing
            # python_files to a pattern nothing matches reads exactly like an
            # empty repository — and silencing the strongest check must cost
            # a refusal, not a note.
            return (
                f"Коммит остановлен: {check.label} не нашёл, что проверять "
                f"({tree}), хотя дерево не пустое.\n\n{output}\n\n"
                "Проверка, которой нечего делать, ничего и не гарантирует.",
                skipped,
            )

        tail = "\n".join(output.splitlines()[-25:])
        return (
            f"Коммит остановлен: {check.label} не прошёл ({tree}).\n\n{tail}\n\n"
            "Почини и повтори.",
            skipped,
        )

    return None, skipped


def _judge(snapshot: Path | None, outside: list[str] | None) -> dict:
    """Decide on the trees that are available, and say which they were.

    Returns the decision rather than printing it. Exactly one decision may
    reach stdout — two concatenated JSON objects are not JSON, and the hook
    that reads them is left with nothing at all.
    """
    trees: list[tuple[str, Path]] = []
    degraded = ""
    if snapshot is not None:
        trees.append((INDEX, snapshot))
    else:
        degraded = (
            "\n\nСнимок индекса собрать не удалось — проверено только "
            f"{WORKTREE}. Это другой код, чем тот, который запишет коммит."
        )
    # None is "git could not say", and it buys the working tree a run rather
    # than costing it one: an unknown difference is not a known absence.
    if outside is None or outside or not trees:
        trees.append((WORKTREE, PROJECT_ROOT))

    reason: str | None = None
    skipped: list[str] = []
    for tree, workdir in trees:
        reason, missing = _run_checks(workdir, tree)
        skipped += [item for item in missing if item not in skipped]
        if reason is not None:
            break

    if reason is not None:
        return _denial(reason + degraded)

    note = REMINDERS + degraded
    note += "\n\nПроверено: " + ", ".join(tree for tree, _ in trees) + "."
    if skipped:
        note += f"\n\nНе проверено:\n{_listing(skipped)}"
    if outside is None:
        note += (
            "\n\nЧем рабочее дерево отличается от индекса, узнать не удалось "
            "(git не ответил) — поэтому дерево проверено на всякий случай."
        )
    elif outside:
        note += (
            "\n\nВ рабочем дереве есть то, чего нет в индексе:\n"
            f"{_listing(outside)}\n"
            "Часть отсюда коммит всё-таки запишет: половинчато "
            "проиндексированный файл уйдёт своей staged-половиной, а git add "
            "в той же командной строке, git commit -a, --only и -p "
            "проиндексируют остальное уже после этой проверки. Поэтому "
            "дерево проверено наравне со снимком."
        )
    return _pass(note)


def _command(payload: object) -> str:
    """The Bash command out of a hook payload, whatever the payload is.

    Anything may arrive on stdin, and every shape that is not the expected
    one has to end in the empty string rather than in an exception. ``[]``
    and ``null`` are valid JSON, and reaching for ``.get`` on them kills a
    hook that then blocks nothing at all.
    """
    if not isinstance(payload, dict):
        return ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("command") or "")


def _decide() -> dict:
    """Run the checks on the trees that exist and return the one decision.

    The temporary directory is made and removed by hand rather than with a
    context manager: ``TemporaryDirectory`` raises from its own cleanup when
    a file is still locked, which Windows does routinely, and an exception
    thrown *after* the decision was reached is the one thing that can turn
    one decision into two.
    """
    outside = _outside_the_index()
    try:
        workspace: str | None = tempfile.mkdtemp(prefix="precommit-gate-")
    except OSError:
        # No temporary directory at all: a full disk, an unwritable TMPDIR.
        workspace = None
    try:
        snapshot = Path(workspace) / "index" if workspace is not None else None
        if snapshot is not None and not _snapshot_index(snapshot):
            snapshot = None
        return _judge(snapshot, outside)
    finally:
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    command = ""
    try:
        command = _command(json.load(sys.stdin))
    except Exception:  # noqa: BLE001 — a hook must never die on its input
        pass

    if "commit" not in command:
        # Not a commit at all. The hook may be registered for every Bash
        # call, and running the suite on `git status` would deny the very
        # commands someone runs to diagnose a failing test.
        return 0

    try:
        decision = _decide()
    except Exception as failure:  # noqa: BLE001 — see below
        # Whatever went wrong, the commit has not been checked. A hook that
        # dies here prints nothing, and a PreToolUse hook that prints nothing
        # blocks nothing: the commit sails through as if the gate had
        # approved it. Refusing is the recoverable direction — it is visible,
        # it names what broke, and it costs one command to override.
        decision = _denial(
            "Коммит остановлен: гейт упал и ничего не проверил.\n\n"
            f"{type(failure).__name__}: {failure}\n\n"
            "Это отказ, а не пропуск: упавшая проверка ничего не гарантирует."
        )

    json.dump({"hookSpecificOutput": decision}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
