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

import yaml

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

    assert config, "pyproject.toml configures nothing under [tool.ruff]"
    assert "line-length" in config, "line length left to ruff's default"
    assert config.get("lint", {}).get("select"), (
        "no explicit rule selection under [tool.ruff.lint]"
    )


def test_the_configured_line_length_is_the_one_contributing_promises():
    """Two numbers that must not drift apart. The document said 100 while ruff
    used its default 88, so `ruff format .` reflowed code the document called
    correctly formatted."""
    promised = re.search(r"Line length:\s*(\d+)", CONTRIBUTING.read_text(encoding="utf-8"))

    assert promised, "CONTRIBUTING.md no longer states a line length"
    assert _ruff_config().get("line-length") == int(promised.group(1))


def _blocking_steps(workflow: str) -> list[str]:
    """Every command a job of this workflow runs and *fails on*.

    Read from the parsed workflow rather than from its text, because being a
    gate is a property of the step and not of the words in it. Two rewrites of
    this check learned that the hard way: matching any line containing
    `ruff check` was satisfied by the explanatory comment above the job, and
    matching any non-comment line was satisfied by a `name:`. Neither noticed a
    `continue-on-error: true` added to the step, which is precisely how a gate
    stops being one while still reading like one.

    A step is skipped here when it is conditional, marked `continue-on-error`,
    or told not to fail — none of those block anything.
    """
    workflow = yaml.safe_load(workflow)
    commands = []
    for job in workflow.get("jobs", {}).values():
        if "if" in job:
            continue
        for step in job.get("steps", []):
            run = step.get("run")
            if not run or step.get("continue-on-error") or "if" in step:
                continue
            commands.extend(line.strip() for line in run.splitlines() if line.strip())
    return commands


def test_ci_blocks_on_the_gate_the_process_calls_a_gate():
    """`docs/process.md` §7.1 lists `ruff check --select F821 .` as a blocking
    check. It was blocking nothing: ruff appeared nowhere in `.github/` except
    as an unchecked box in the PR template, which is an honour system, not a
    gate. "Runs somewhere in CI" is not the claim — "fails the build" is."""
    blocking = _blocking_steps(CI_WORKFLOW.read_text(encoding="utf-8"))

    gate = [line for line in blocking if line.startswith("ruff check")]

    assert gate, "no blocking step in ci.yml runs ruff"
    assert any(f"--select {GATE_RULE}" in line for line in gate), (
        f"ci.yml runs ruff but nothing blocking runs the {GATE_RULE} gate: {gate}"
    )


def test_a_step_that_cannot_fail_is_not_a_gate():
    """The guard on the guard above, kept as a test so the distinction cannot
    be refactored away by someone who does not know it was ever a problem.
    Every shape below kept an earlier version of this file green while the
    gate was disabled."""
    gate = "jobs:\n  lint:\n    steps:\n      - name: g\n        run: ruff check --select F821 .\n"

    assert _blocking_steps(gate) == ["ruff check --select F821 ."]
    assert _blocking_steps(gate.replace("        run:", "        continue-on-error: true\n        run:")) == []
    assert _blocking_steps(gate.replace("  lint:\n", "  lint:\n    if: false\n")) == []
    assert _blocking_steps("jobs:\n  lint:\n    steps:\n      - name: ruff check --select F821 .\n") == []


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

    # Asserted, not assumed: the `pre-commit` clause below is a conditional,
    # and a conditional over an empty list passes without reading anything.
    # Deleting the lint section wholesale used to leave this test green.
    assert any(command.startswith("ruff check") for command in commands), (
        "CONTRIBUTING.md no longer tells contributors how to run the linter"
    )

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
