"""The tier-2 end-to-end run is a manual step, and that has to stay true.

`tests/test_e2e_tier2_semantic.py` runs the whole pipeline and compares the
result to a frozen baseline. It carries `slow` and `requires_asr`, and CI
deselects both — so it has never run in CI and, by decision, never will: the
faster-whisper bundle it needs is ~3.2 GB (ADR-022).

`CONTRIBUTING.md` therefore hands the run to a person and says when it is owed.
That promise rests on two facts about this repository, and both can rot without
anyone noticing: the markers can come off the tier-2 tests, and CI can grow a
pytest invocation that collects them. Either one turns the document into a lie
while every other check stays green.

These tests check that pair, plus that the section making the promise still
names the module and both moments. They deliberately do not run the tier-2
suite: the decision was that running it costs 3.2 GB, and a test enforcing it
would re-impose the cost the decision refused.

What they cannot check is whether anybody actually ran it. That half is a
promise, and it is meant to read as one.
"""

from __future__ import annotations

import ast
import shlex
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TIER2 = PROJECT_ROOT / "tests" / "test_e2e_tier2_semantic.py"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

#: The markers that keep the tier-2 run out of CI. Named here so that dropping
#: one is a failure with a reason, not a silent widening of what CI is on the
#: hook for.
KEEPS_IT_OUT = frozenset({"slow", "requires_asr"})

#: Options whose *next* token is a value rather than a target path. Without
#: this list `-k something` would read `something` as a file to collect.
TAKES_A_VALUE = frozenset(
    {"-m", "-k", "-p", "-n", "-c", "-o", "-W", "--deselect", "--ignore", "--junitxml"}
)


# ── reading the markers off the tier-2 module ───────────────────────────────


def _mark_name(decorator: ast.expr) -> str | None:
    """The marker name in a `@pytest.mark.NAME` decorator, or None.

    Insisting on the `pytest.mark` prefix matters: a project-local
    `@helpers.slow` would otherwise be counted as the marker that keeps the
    suite out of CI, which pytest would not agree with.
    """
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Attribute):
        return None
    owner = node.value
    if owner.attr != "mark":
        return None
    if not isinstance(owner.value, ast.Name) or owner.value.id != "pytest":
        return None
    return node.attr


def _module_level_marks(tree: ast.Module) -> frozenset[str]:
    """Markers applied to the whole module via `pytestmark`.

    `pytestmark = [pytest.mark.slow, pytest.mark.requires_asr]` is the ordinary
    way to mark a whole file, and it is exactly equivalent to decorating each
    test. A check that only read decorators would call that refactor a
    regression.
    """
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        value = node.value
        elements = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        names.update(name for name in map(_mark_name, elements) if name)
    return frozenset(names)


def _markers_on_tests(module: Path) -> dict[str, frozenset[str]]:
    """Map every `test_*` function in *module* to the markers pytest sees on it.

    Read from the syntax tree rather than by importing: the module skips itself
    at import time when the faster-whisper bundle is missing, which is every
    machine this check runs on.

    Walked in full rather than over the module body, because a test added
    inside a `class Test…` is collected by pytest just the same — and an
    unmarked one there is precisely the regression this file exists to catch.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    inherited = _module_level_marks(tree)
    found: dict[str, frozenset[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        own = {name for name in map(_mark_name, node.decorator_list) if name}
        found[node.name] = frozenset(own | inherited)
    return found


# ── reading the pytest invocations out of the workflow ──────────────────────


def _pytest_invocations() -> list[tuple[list[str], str | None]]:
    """Every pytest invocation in the CI workflow, as (targets, -m expression).

    All of them, not the first: a second step is how the tier-2 suite would
    actually come back — a nightly job, or a step naming the file directly with
    no `-m` at all. A check that read one step would stay green through both.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    invocations: list[tuple[list[str], str | None]] = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            script = step.get("run", "")
            if "pytest" not in script:
                continue
            for line in script.replace("\\\n", " ").splitlines():
                invocations.extend(_invocations_in(line))
    return invocations


def _invocations_in(line: str) -> list[tuple[list[str], str | None]]:
    try:
        tokens = shlex.split(line, comments=True)
    except ValueError:  # unbalanced quotes — unreadable, so unchecked
        raise AssertionError(f"cannot read this CI command line: {line!r}") from None

    found = []
    for index, token in enumerate(tokens):
        if token != "pytest" and not token.endswith("/pytest"):
            continue
        found.append(_parse_arguments(tokens[index + 1 :]))
    return found


def _parse_arguments(arguments: list[str]) -> tuple[list[str], str | None]:
    targets: list[str] = []
    expression: str | None = None
    skip_next = False
    for index, token in enumerate(arguments):
        if skip_next:
            skip_next = False
            continue
        if token in TAKES_A_VALUE:
            skip_next = True
            if token == "-m" and index + 1 < len(arguments):
                expression = arguments[index + 1]
            continue
        if token.startswith("-"):
            continue
        targets.append(token)
    return targets, expression


def _collects(targets: list[str], module: Path) -> bool:
    """Would a pytest run over *targets* collect *module*?

    No targets means pytest falls back to `testpaths` from pytest.ini, which is
    the whole `tests` tree — so an argument-less run collects it too.
    """
    relative = module.relative_to(PROJECT_ROOT)
    if not targets:
        targets = ["tests"]
    for target in targets:
        path = Path(target.split("::")[0])
        if path == relative or path in relative.parents:
            return True
    return False


def _selects(expression: str | None, markers: frozenset[str]) -> bool:
    """Evaluate a pytest `-m` expression against a set of marker names.

    No expression selects everything — that is the form a step naming the file
    directly would take, and reading it as "selects nothing" would make the
    dangerous case invisible.

    Evaluating beats matching on substrings: `not slow and not requires_asr`
    and `not (slow or requires_asr)` mean the same thing, and a check that
    understood only one would fail on a rewrite that changed nothing.
    """
    if expression is None:
        return True

    def value(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in markers
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not value(node.operand)
        if isinstance(node, ast.BoolOp):
            results = [value(operand) for operand in node.values]
            return all(results) if isinstance(node.op, ast.And) else any(results)
        raise AssertionError(f"unsupported marker expression: {ast.dump(node)}")

    return value(ast.parse(expression, mode="eval").body)


# ── the checks ──────────────────────────────────────────────────────────────


def test_the_tier2_tests_carry_the_markers_that_keep_them_out_of_ci():
    markers = _markers_on_tests(TIER2)
    assert markers, f"{TIER2.name} collects no test functions"
    for name, on_test in markers.items():
        missing = KEEPS_IT_OUT - on_test
        assert not missing, (
            f"{name} lost {sorted(missing)}. CONTRIBUTING.md says CI never runs the "
            f"tier-2 suite; without these markers CI would try, and fail for want "
            f"of a 3.2 GB model bundle."
        )


def test_no_pytest_step_in_ci_runs_the_tier2_suite():
    invocations = _pytest_invocations()
    assert invocations, (
        "no pytest invocation found in ci.yml. Either CI stopped running tests, "
        "or this check stopped being able to read it — both make it worthless."
    )
    markers = _markers_on_tests(TIER2)
    for targets, expression in invocations:
        if not _collects(targets, TIER2):
            continue
        for name, on_test in markers.items():
            assert not _selects(expression, on_test), (
                f"CI would run {name}: targets {targets or ['(testpaths)']} with "
                f"-m {expression!r}. That is a change of decision, not of code — "
                f"either CI grew a model bundle, or CONTRIBUTING.md and ADR-022 "
                f"are now lying about who runs this suite."
            )


def test_at_least_one_ci_step_would_have_collected_it():
    """Guards the check above against passing because nothing matched.

    Every clause in it is a `continue` away from vacuous truth: no invocation,
    none collecting the file. If CI ever stops covering `tests/` at all, this
    is what says so.
    """
    invocations = _pytest_invocations()
    assert any(_collects(targets, TIER2) for targets, _ in invocations), (
        "no pytest step in ci.yml collects tests/test_e2e_tier2_semantic.py at "
        "all — so the check that CI deselects it proves nothing."
    )


def test_the_reader_tells_the_dangerous_shapes_apart():
    """The parsing has to be able to fail, or the checks above prove nothing."""
    # A second step that runs exactly what the first one excluded.
    targets, expression = _invocations_in('pytest tests -m "slow and requires_asr" -v')[0]
    assert _collects(targets, TIER2)
    assert _selects(expression, frozenset({"slow", "requires_asr"}))

    # A step naming the file directly, with no marker selection at all.
    targets, expression = _invocations_in("pytest tests/test_e2e_tier2_semantic.py -v")[0]
    assert _collects(targets, TIER2)
    assert _selects(expression, frozenset({"slow", "requires_asr"}))

    # The forms the real workflow may take, none of which run it.
    for line in (
        'pytest tests -m "not slow and not requires_asr" -v',
        'python -m pytest tests/ -m "not (slow or requires_asr)"',
        'pytest -m "not slow and not requires_asr" tests -v',
        'pytest -k something tests -m "not slow and not requires_asr"',
    ):
        targets, expression = _invocations_in(line)[0]
        assert _collects(targets, TIER2), line
        assert not _selects(expression, frozenset({"slow", "requires_asr"})), line

    # A run over an unrelated file does not collect it, whatever it selects.
    targets, _ = _invocations_in("pytest tests/test_build_spec.py -v --noconftest")[0]
    assert not _collects(targets, TIER2)

    # `-k` is a value, not a path.
    targets, _ = _invocations_in("pytest -k tests tests/test_build_spec.py")[0]
    assert targets == ["tests/test_build_spec.py"]


# ── the document that carries the half a machine cannot check ───────────────


def _tier2_section() -> str:
    """The body of the CONTRIBUTING section about the tier-2 run.

    Scoped to the section, and fence-aware: `release` appears elsewhere in a
    file this long, and `# One-time bundle install` inside a ```bash block is a
    shell comment, not a heading. Reading either one wrong makes the assertions
    below pass or fail on text nobody wrote for them.
    """
    lines = CONTRIBUTING.read_text(encoding="utf-8").splitlines()
    inside_fence = False
    start = None
    depth = 0
    body: list[str] = []
    for line in lines:
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            if start is not None:
                body.append(line)
            continue
        heading = not inside_fence and line.startswith("#")
        if start is None:
            if heading and "tier-2" in line.lower():
                start = line
                depth = len(line) - len(line.lstrip("#"))
            continue
        if heading and (len(line) - len(line.lstrip("#"))) <= depth:
            break
        body.append(line)
    assert start is not None, (
        "CONTRIBUTING.md has no heading about the tier-2 run. CI does not run "
        "that suite; if the document does not say who does, nobody does."
    )
    return "\n".join(body)


def test_contributing_says_when_the_manual_run_is_owed():
    section = _tier2_section()
    assert "tests/test_e2e_tier2_semantic.py" in section, (
        "the tier-2 section does not name the module it is about. The suite is "
        "nobody's job unless the document says which suite."
    )
    for trigger in ("release", "sources/", "mergers/"):
        assert trigger in section, (
            f"the tier-2 section does not name {trigger!r} as a moment the run is "
            f"owed. 'Run it sometimes' is not an obligation."
        )


def test_the_section_reader_stops_at_the_next_heading_not_at_a_shell_comment():
    """The fence handling is the whole reason the check above reads the section.

    Moving the install block above the bullets is an ordinary edit to a
    document; before this, it truncated the section and turned the check red on
    text that was entirely correct.
    """
    section = _tier2_section()
    assert "```bash" in section, (
        "the tier-2 section no longer contains its command block — the reader "
        "is cutting the section short again."
    )
    assert "pytest tests/test_e2e_tier2_semantic.py" in section
