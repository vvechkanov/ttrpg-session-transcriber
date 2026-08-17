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

On success the gate is not silent: it hands back the two questions that green
tests do not answer, plus anything that weakens the guarantee it just gave.
"""

from __future__ import annotations

import json
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

CHECKS: list[tuple[str, list[str]]] = [
    (
        "ruff F821 (undefined names)",
        [PYTHON, "-m", "ruff", "check", "--select", "F821", "--quiet", "."],
    ),
    (
        "pytest (fast suite)",
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
    """Tracked files modified but not staged, outside the staged set."""
    staged = set(_git("diff", "--cached", "--name-only"))
    return sorted(set(_git("diff", "--name-only")) - staged)


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


def _is_module_missing(output: str) -> bool:
    """True when the failure is "this tool is not installed".

    ``python -m <tool>`` starts the interpreter successfully and only then
    fails, so a missing tool arrives as a non-zero exit rather than as
    FileNotFoundError.
    """
    return "No module named" in output


def main() -> int:
    # The payload is read and discarded: the `if` filter in settings.json
    # already restricts this hook to `git commit`, so there is nothing
    # here worth re-deciding.
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001 — a hook must never die on its input
        pass

    conflicted = _staged_but_dirty()
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

    for label, command in CHECKS:
        try:
            result = subprocess.run(
                command,
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
        if _is_module_missing(output):
            skipped.append(f"{label}: не установлен")
            continue

        tail = "\n".join(output.splitlines()[-25:])
        _deny(f"Коммит остановлен: {label} не прошёл.\n\n{tail}\n\nПочини и повтори.")
        return 0

    note = REMINDERS
    if skipped:
        listing = "\n".join(f"  - {item}" for item in skipped)
        note += f"\n\nНе проверено (инструмента нет):\n{listing}"
    dirty = _dirty_elsewhere()
    if dirty:
        listing = "\n".join(f"  - {path}" for path in dirty)
        note += (
            "\n\nВ рабочем дереве есть незаиндексированные правки — тесты "
            f"гонялись вместе с ними, в коммит они не попадут:\n{listing}"
        )
    _allow_with_note(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
