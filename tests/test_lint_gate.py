"""The linter has to be a gate, not a promise.

`CONTRIBUTING.md` has been telling contributors for months that ruff is
configured in `pyproject.toml` and holds lines to 100 characters. Neither was
true: there was no `[tool.ruff]` section at all, so the default 88 applied, and
no CI step ran ruff even once. A style rule nobody runs is not a style rule,
and a document describing one that does not exist costs more than silence —
it is believed.

These tests check the three claims a machine can check: the config exists, CI
runs the gate the process document calls a gate, and `CONTRIBUTING.md` promises
only tooling this repository actually ships.

They deliberately do not check *which* rules are enabled beyond the gate — the
rule set is a separate decision with its own card, and freezing it here would
make that decision harder to land rather than easier.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

#: The rule the process document (`docs/process.md` §7.1) names as the gate in
#: force today. It is already green, so wiring it into CI blocks nothing
#: retroactively — which is the whole reason it is the one that goes in first.
GATE_RULE = "F821"


def _ruff_config() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8")).get("tool", {}).get("ruff", {})


def test_ruff_is_configured_in_pyproject():
    """`CONTRIBUTING.md` says "config in `pyproject.toml`". Until this passes
    that sentence is false, and every contributor gets whatever defaults their
    locally installed ruff happens to ship — a moving target across versions."""
    config = _ruff_config()

    assert config, "pyproject.toml has no [tool.ruff] section"
    assert "line-length" in config, "line length left to ruff's default"
    assert config.get("lint", {}).get("select"), "no explicit rule selection"


def test_the_configured_line_length_is_the_one_contributing_promises():
    """Two numbers that must not drift apart. The document said 100 while ruff
    used its default 88, so `ruff format .` reflowed code the document called
    correctly formatted."""
    promised = re.search(r"Line length:\s*(\d+)", CONTRIBUTING.read_text(encoding="utf-8"))

    assert promised, "CONTRIBUTING.md no longer states a line length"
    assert _ruff_config().get("line-length") == int(promised.group(1))


def _ruff_invocations(workflow: str) -> list[str]:
    """Lines of the workflow that actually run ruff.

    Comments are dropped, and that is the whole reason this is a function: the
    first version of this check counted any line mentioning `ruff check`, and
    the comment above the job — which quotes the gate verbatim to explain it —
    kept the test green after the real step had been changed to something else.
    A check satisfied by a sentence about the check is worse than none.
    """
    return [
        stripped
        for line in workflow.splitlines()
        if "ruff check" in (stripped := line.strip()) and not stripped.startswith("#")
    ]


def test_ci_runs_the_gate_the_process_calls_a_gate():
    """`docs/process.md` §7.1 lists `ruff check --select F821 .` as a blocking
    check. It was blocking nothing: ruff appeared nowhere in `.github/` except
    as an unchecked box in the PR template, which is an honour system, not a
    gate."""
    invocations = _ruff_invocations(CI_WORKFLOW.read_text(encoding="utf-8"))

    assert invocations, "no step in ci.yml runs ruff"
    assert any(GATE_RULE in line for line in invocations), (
        f"ci.yml runs ruff but not the {GATE_RULE} gate: {invocations}"
    )


def test_a_comment_about_the_gate_is_not_the_gate():
    """The guard on the guard above, kept as a test so the distinction cannot
    be refactored away by someone who does not know it was ever a problem."""
    assert _ruff_invocations("  # runs ruff check --select F821 . every push") == []
    assert _ruff_invocations("  run: ruff check --select F821 .") == [
        "run: ruff check --select F821 ."
    ]


def _commands(markdown: str) -> list[str]:
    """Lines inside fenced blocks — what the document tells a reader to *run*.

    Prose that names a command is not an instruction to run it, and the
    difference matters here: the note explaining that `pre-commit` never
    worked has to be able to say so without tripping the check that put it
    there.
    """
    inside, lines = False, []
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside and line.strip():
            lines.append(line.strip())
    return lines


def test_contributing_tells_contributors_to_run_only_what_exists():
    """`pre-commit install` sat in a bash block as a documented shortcut that
    would "run the same checks" — with no `.pre-commit-config.yaml` anywhere in
    the tree, so it failed outright. A contributor following the document lands
    on an error with no way to tell whether they broke something or it did."""
    commands = _commands(CONTRIBUTING.read_text(encoding="utf-8"))

    if any(command.startswith("pre-commit") for command in commands):
        assert (PROJECT_ROOT / ".pre-commit-config.yaml").exists(), (
            "CONTRIBUTING.md tells contributors to run pre-commit, "
            "but this repository ships no .pre-commit-config.yaml"
        )


def test_the_command_reader_tells_prose_from_instruction():
    """A guard on the guard: a rule that stopped seeing fenced blocks would
    pass silently, and silence is what this whole file exists to remove."""
    assert _commands("run it:\n```bash\npre-commit install\n```\n") == ["pre-commit install"]
    assert _commands("we removed `pre-commit install` because it never worked") == []
