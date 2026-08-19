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
PROCESS = PROJECT_ROOT / "docs" / "process.md"

#: How `docs/process.md` §7.1 writes the gate it declares blocking.
DOCUMENTED_GATE = re.compile(r"`ruff check --select (\w+) \.`")


def _documented_gate() -> str:
    """The rule the process document calls the gate — read, not restated.

    Hard-coding `F821` here would have made this file its own authority: the
    day §7.1 declares a different rule, a test that carries its own copy of
    the answer keeps passing while CI stays on the old one. The document is
    where the decision lives, so the document is what gets read.
    """
    named = set(DOCUMENTED_GATE.findall(PROCESS.read_text(encoding="utf-8")))

    assert len(named) == 1, f"docs/process.md §7.1 names {named or 'no'} ruff gate"
    return named.pop()


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


#: Shell syntax that decides the exit status of a line by something other than
#: the command at its head: `||`, `;`, `&&`, a pipeline, a redirect, a
#: subshell. Listing the *neutralizers* instead — `|| true`, `; true` — was the
#: previous attempt, and it lost: `|| echo lint-failed` is not on any such
#: list and still hands the line `echo`'s exit status. So the rule is inverted.
#: A gate has to be a plain command, and anything with a joint in it is not
#: counted as one, however it ends up behaving.
SHELL_PLUMBING = ("|", "&", ";", ">", "<", "$(", "`", "(", ")")

#: The one flag that neutralises ruff without any shell syntax at all — and the
#: workflow's own report-only step uses it, which is what makes it easy to
#: forget it is there.
SELF_NEUTRALIZING = ("--exit-zero",)


def _blocking_steps(workflow: str) -> list[str]:
    """Every command a job of this workflow runs and *fails on*.

    Read from the parsed workflow rather than from its text, because being a
    gate is a property of the step and not of the words in it. Three rewrites
    of this check learned that in stages. Matching any line containing
    `ruff check` was satisfied by the explanatory comment above the job.
    Matching any non-comment line was satisfied by a `name:`. Reading the
    parsed steps caught a `continue-on-error: true` and an `if: false` — but
    still counted a command handed `--exit-zero`; blacklisting *that* still
    counted `|| echo lint-failed`, which is not on any list of tricks and
    hands the line `echo`'s exit status all the same.

    Chasing that list is unwinnable, so the rule is inverted: a command counts
    only if it is *plainly* a command — no shell plumbing to decide its exit
    status for it, no `--exit-zero`, no `continue-on-error`, and no `if` on
    the step or its job. Anything more elaborate is not counted, which at
    worst under-reports; the tests here ask whether a gate exists, so the
    conservative direction is the safe one.
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
            commands.extend(
                stripped
                for line in run.splitlines()
                if (stripped := line.strip())
                and not any(joint in stripped for joint in SHELL_PLUMBING)
                and not any(flag in stripped for flag in SELF_NEUTRALIZING)
            )
    return commands


def test_ci_blocks_on_the_gate_the_process_calls_a_gate():
    """`docs/process.md` §7.1 lists a ruff rule as a blocking check. It was
    blocking nothing: ruff appeared nowhere in `.github/` except as an
    unchecked box in the PR template, which is an honour system, not a gate.
    "Runs somewhere in CI" is not the claim — "fails the build" is, and the
    rule it has to run is whichever one the document currently names."""
    rule = _documented_gate()
    blocking = _blocking_steps(CI_WORKFLOW.read_text(encoding="utf-8"))

    gate = [line for line in blocking if line.startswith("ruff check")]

    assert gate, "no blocking step in ci.yml runs ruff"
    assert any(f"--select {rule}" in line for line in gate), (
        f"docs/process.md calls {rule} the gate; nothing blocking in ci.yml runs it: {gate}"
    )


def test_the_gate_is_read_from_the_document_not_restated():
    """The guard on `_documented_gate`: if the regex ever stops matching, the
    test above would be asserting against whatever it happened to return."""
    assert _documented_gate() in PROCESS.read_text(encoding="utf-8")
    assert DOCUMENTED_GATE.findall("| `ruff check --select F401 .` | CI |") == ["F401"]


def test_a_step_that_cannot_fail_is_not_a_gate():
    """The guard on the guard above, kept as a test so the distinction cannot
    be refactored away by someone who does not know it was ever a problem.
    Every shape below kept an earlier version of this file green while the
    gate was disabled."""
    gate = "jobs:\n  lint:\n    steps:\n      - name: g\n        run: ruff check --select F821 .\n"

    disabled = "        continue-on-error: true\n        run:"

    assert _blocking_steps(gate) == ["ruff check --select F821 ."]
    assert _blocking_steps(gate.replace("        run:", disabled)) == []
    assert _blocking_steps(gate.replace("  lint:\n", "  lint:\n    if: false\n")) == []
    assert _blocking_steps("jobs:\n  lint:\n    steps:\n      - name: ruff check --select F821 .\n") == []
    # The command can neutralise itself without the workflow saying a word —
    # and the report-only step in this very file does exactly that.
    assert _blocking_steps(gate.replace("F821 .", "F821 . --exit-zero")) == []
    # Shapes a list of known tricks would have to grow to cover, one by one.
    for tail in ("|| true", "|| echo lint-failed", "; echo done", "| tee out.txt", "&& true"):
        assert _blocking_steps(gate.replace("F821 .", f"F821 . {tail}")) == [], tail


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
