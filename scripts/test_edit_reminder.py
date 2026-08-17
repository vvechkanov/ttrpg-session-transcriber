"""Nudge after a test file is written, at the moment it can still be fixed.

Wired as a Claude Code PostToolUse hook on Write|Edit. Stays silent for every
file outside ``tests/``.

The three questions below separate a test that would catch a regression from
one that only looks like it would.
"""

from __future__ import annotations

import json
import sys

LESSON = (
    "Тест только что изменён. Три вопроса:\n"
    "  1. Тест вызывает продакшн-код — или переписывает его логику "
    "у себя? Переписанная логика зеленеет, когда настоящая падает.\n"
    "  2. Проверяемое значение считает продакшн — или его подставил "
    "сам тест? Второе прячет то, что продакшн его не считает вовсе.\n"
    "  3. Ассерт различает «работает» и «сломано»? "
    "`phase != \"asr\"` проходит и на \"idle\".\n"
    "Если не уверен — сломай продакшн-код мутацией и убедись, что тест "
    "покраснел."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — a hook must never die on its input
        return 0

    tool_input = payload.get("tool_input") or {}
    response = payload.get("tool_response") or {}
    path = str(response.get("filePath") or tool_input.get("file_path") or "")
    if not path:
        return 0

    normalised = path.replace("\\", "/")
    is_test = "/tests/" in normalised or normalised.startswith("tests/")
    if not is_test or not normalised.endswith(".py"):
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": LESSON,
            },
            "suppressOutput": True,
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
