"""The tier-2 end-to-end run is a manual step, and that has to be written down.

`tests/test_e2e_tier2_semantic.py` is the only check that runs the whole
pipeline and compares the result to a frozen baseline. It carries `slow` and
`requires_asr`, and CI deselects both — so it has never run in CI and, by
decision, never will: the faster-whisper bundle it needs is ~3.2 GB.

A check nobody runs is not a check. The decision (card «[тесты 5/5]») was to
keep it manual and make the obligation explicit in `CONTRIBUTING.md` instead of
pretending CI covers it. That turns the guarantee into a promise a human keeps,
and a promise is only worth what the document says about *when* it comes due.

These tests check the three claims a machine can check: the tier-2 tests really
are marked the way the document says, CI's selection really does exclude them,
and `CONTRIBUTING.md` really does name the module and both moments it is owed.

They deliberately do not run the tier-2 suite. The point of the decision was
that running it costs 3.2 GB; a test that enforced it would re-impose the cost
the decision refused.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TIER2 = PROJECT_ROOT / "tests" / "test_e2e_tier2_semantic.py"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

#: The markers that keep the tier-2 run out of CI. Named here so that dropping
#: one from the test module is a failure with a reason, not a silent widening
#: of what CI is on the hook for.
KEEPS_IT_OUT = frozenset({"slow", "requires_asr"})


def _markers_on_tests(module: Path) -> dict[str, frozenset[str]]:
    """Map each ``test_*`` function in *module* to its `pytest.mark.*` names.

    Read from the syntax tree rather than by importing: the module skips itself
    at import time when the faster-whisper bundle is missing, which is every
    machine this test runs on.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    found: dict[str, frozenset[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        names = set()
        for decorator in node.decorator_list:
            attribute = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(attribute, ast.Attribute):
                names.add(attribute.attr)
        found[node.name] = frozenset(names)
    return found


def _ci_marker_expression() -> str:
    """The ``-m`` expression CI's pytest step selects with."""
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run", "")
            if "pytest tests " in run and " -m " in run:
                _, _, rest = run.partition(" -m ")
                quoted = rest.lstrip()
                assert quoted[:1] in ('"', "'"), f"CI's -m expression is not quoted: {run!r}"
                closing = quoted.index(quoted[0], 1)
                return quoted[1:closing]
    raise AssertionError("no pytest step with a marker selection found in ci.yml")


def _selects(expression: str, markers: frozenset[str]) -> bool:
    """Evaluate a pytest ``-m`` expression against a set of marker names.

    Evaluating beats matching on substrings: `not slow and not requires_asr`
    and `not (slow or requires_asr)` mean the same thing, and a test that
    understood only one of them would fail on a rewrite that changed nothing.
    """

    def value(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in markers
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not value(node.operand)
        if isinstance(node, ast.BoolOp):
            results = [value(operand) for operand in node.values]
            return all(results) if isinstance(node.op, ast.And) else any(results)
        raise AssertionError(f"unsupported marker expression node: {ast.dump(node)}")

    return value(ast.parse(expression, mode="eval").body)


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


def test_ci_deselects_every_tier2_test():
    expression = _ci_marker_expression()
    for name, on_test in _markers_on_tests(TIER2).items():
        assert not _selects(expression, on_test), (
            f"CI's selection {expression!r} now runs {name}. That is a change of "
            f"decision, not a change of code: either CI grew a model cache, or "
            f"CONTRIBUTING.md is now lying about who runs this suite."
        )


def test_the_selection_would_notice_if_it_stopped_excluding_them():
    """The evaluator has to be able to fail, or the test above proves nothing."""
    assert _selects("not gui", frozenset({"slow", "requires_asr"}))
    assert not _selects("not slow and not requires_asr", frozenset({"slow"}))
    assert not _selects("not (slow or requires_asr)", frozenset({"requires_asr"}))
    assert _selects("slow and requires_asr", frozenset({"slow", "requires_asr"}))


def _tier2_section() -> str:
    """The body of the CONTRIBUTING section about the tier-2 run.

    Scoped to the section rather than the whole document on purpose: `release`
    appears elsewhere in a file this long, and an obligation satisfied by a
    word in an unrelated paragraph is not an obligation.
    """
    lines = CONTRIBUTING.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("#") and "tier-2" in line.lower():
            depth = len(line) - len(line.lstrip("#"))
            body = []
            for following in lines[index + 1 :]:
                if following.startswith("#") and (
                    len(following) - len(following.lstrip("#")) <= depth
                ):
                    break
                body.append(following)
            return "\n".join(body)
    raise AssertionError(
        "CONTRIBUTING.md has no heading about the tier-2 run. CI does not run "
        "that suite; if the document does not say who does, nobody does."
    )


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
