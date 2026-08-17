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

On success the gate is not silent: it hands back the two questions that green
tests do not answer.
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


def main() -> int:
    # The payload is read and discarded: the `if` filter in settings.json
    # already restricts this hook to `git commit`, so there is nothing
    # here worth re-deciding.
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001 — a hook must never die on its input
        pass

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
            # Tooling missing is not a reason to block a commit — say so
            # and move on, or a fresh clone becomes uncommittable.
            continue
        except subprocess.TimeoutExpired:
            _deny(f"{label}: не уложился в 180 с. Запусти вручную и посмотри.")
            return 0

        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            tail = "\n".join(output.splitlines()[-25:])
            _deny(
                f"Коммит остановлен: {label} не прошёл.\n\n{tail}\n\n"
                "Почини и повтори."
            )
            return 0

    _allow_with_note(REMINDERS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
