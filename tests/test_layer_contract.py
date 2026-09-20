"""The layer rules have to be a gate, not a paragraph.

`ARCHITECTURE.md` §3 writes the dependency rules out strictly and then says,
in the same breath, that they are held by «дисциплиной + ревью». It is right:
measured on the tree before this landed, a `from mergers.script_merger import
ScriptMerger` added to `ui/models/session.py` — an edge §3 forbids by name —
left `ruff check --select F821 .` green and all 952 tests passing. The full
ruff set moved by exactly one finding, `F401 unused-import`, which would have
disappeared the moment the import was used.

`lint-imports` itself is what checks the tree; these tests check the things
`lint-imports` cannot check about *itself*:

* that CI fails on it, rather than merely mentioning it;
* that `docs/process.md` §7.1 has stopped calling it work ahead — §7.1's own
  preamble says a «планируется» row "не блокирует ничего и не является
  проверкой", so leaving the row behind would make the document lie in the
  one place an agent is told to trust;
* that the contract keeps the two settings without which it reads as a gate
  and is not one.

That last group is the reason this file is longer than "we added a tool". A
`layers` contract forbids importing upwards and between independent siblings;
importing *downwards past a level* it allows. All eight known violations are
that shape, so a layers-only configuration reports `KEPT` on the very debt §3
writes out by hand. Both settings below are what close that gap, and both are
one word long — which is exactly how they get lost.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

# Reused rather than copied: deciding whether a workflow step can fail is
# subtle enough that `test_lint_gate` carries a docstring about the three
# rewrites that got it wrong, and a second copy would be a second thing to
# get wrong. Importing it also means a fix there reaches here.
from tests.test_lint_gate import _blocking_steps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
ARCHITECTURE = PROJECT_ROOT / "ARCHITECTURE.md"
PROCESS = PROJECT_ROOT / "docs" / "process.md"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

#: A bullet of §3's "Dependency rules (строго)" — «- `ui` → `core`». The names
#: are read from the document for the reason `test_lint_gate` reads the ruff
#: rule from §7.1: a list hard-coded here would make this file its own
#: authority, and the day §3 gains or loses a layer the test keeps passing
#: against yesterday's architecture.
RULE_LINE = re.compile(r"^- `(\w+)` → (.+)$", re.MULTILINE)


def _importlinter_config() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["importlinter"]


def _contracts() -> list[dict]:
    return _importlinter_config()["contracts"]


def _layers_named_by_architecture() -> set[str]:
    """The layer names §3 writes in its dependency rules, read from §3."""
    section = ARCHITECTURE.read_text(encoding="utf-8")
    section = section[section.index("### Dependency rules") :]
    section = section[: section.index("### Запрещено")]

    names: set[str] = set()
    for source, targets in RULE_LINE.findall(section):
        names.add(source)
        names.update(re.findall(r"`(\w+)`", targets))
    return names


def test_the_six_root_packages_are_the_six_layers_the_document_names():
    """§3 says «шесть папок, каждая соответствует слою». If the contract
    watches five of them, the sixth is unguarded and nothing says so."""
    named = _layers_named_by_architecture()

    assert len(named) == 6, f"§3's dependency rules name {sorted(named)}, expected six"
    assert set(_importlinter_config()["root_packages"]) == named


def test_every_watched_package_is_a_real_package():
    """A root package that does not exist is not an error for import-linter —
    it simply contributes nothing to the graph, and the contracts above it go
    green for want of anything to check."""
    for package in _importlinter_config()["root_packages"]:
        assert (PROJECT_ROOT / package / "__init__.py").is_file(), (
            f"root_packages names {package}, which is not a package in this tree"
        )


def _adjacency_contract() -> dict:
    """The `forbidden` contract standing for §3's «ui → core», i.e. the rule
    that `ui` reaches the lower layers *through* `core` and not past it."""
    forbidden = [c for c in _contracts() if c["type"] == "forbidden"]

    assert len(forbidden) == 1, f"expected one forbidden contract, found {len(forbidden)}"
    return forbidden[0]


def test_the_adjacency_rule_is_checked_at_all():
    """The contract the card is actually about.

    A `layers` contract alone reports `Six layers KEPT` on this tree: the
    eight violations §3 lists are all downward-past-a-level, which `layers`
    permits. Deleting this contract — or the flag below — would leave a CI
    job that passes, a `pyproject.toml` that reads as if the debt were
    watched, and a gate that catches nothing."""
    contract = _adjacency_contract()

    assert contract["source_modules"] == ["ui"]
    assert set(contract["forbidden_modules"]) == {"sources", "mergers", "renderers", "domain"}


def test_indirect_imports_stay_allowed():
    """Without `allow_indirect_imports` the same contract also reports the
    transitive chains §3 *permits* — `ui.cli → core → core.pipeline →
    domain.annotations` and 28 more. A contract that red-flags legal
    architecture gets switched off, and then nothing is checked."""
    assert _adjacency_contract()["allow_indirect_imports"] is True


def test_a_repaired_violation_cannot_leave_its_exception_behind():
    """The eight exceptions record debt that is scheduled to be repaid
    (F-C1). An `ignore_imports` entry matching nothing passes silently —
    `lint-imports` prints `KEPT (8 ignored imports)` and says nothing about
    any of them being fiction. Measured both ways: a ninth entry naming an
    edge that does not exist fails the run with `error` and passes with
    `none`. So the day an edge is repaired is a red build naming the stale
    line, not eight lines of decoration nobody reads."""
    assert _adjacency_contract()["unmatched_ignore_imports_alerting"] == "error"


def test_the_known_violations_are_listed_rather_than_waived_wholesale():
    """Debt is named edge by edge. A directory-wide waiver — ignoring
    `ui.engines -> *`, or dropping `ui.engines` from the graph — would take
    the whole module out of the gate, and `ui/engines` is where every one of
    the eight lives: the next one would be invisible too."""
    ignored = _adjacency_contract()["ignore_imports"]

    assert ignored, "no exceptions listed; §3 says eight edges violate the rule today"
    for entry in ignored:
        source, _, target = entry.partition(" -> ")
        assert source.startswith("ui.engines."), f"{entry!r} waives more than one module"
        assert "*" not in entry, f"{entry!r} is a wildcard, not a named edge"


def test_ci_blocks_on_the_layer_contracts():
    """"Mentioned in CI" is not the claim — "fails the build" is. §7.1 calls
    this a CI gate, and `spec-lint` and the ruff gate are both jobs that fail;
    a step handed `|| true`, `--exit-zero` or a `continue-on-error` would read
    identically in the file and block nothing."""
    blocking = _blocking_steps(CI_WORKFLOW.read_text(encoding="utf-8"))

    assert any(line.startswith("lint-imports") for line in blocking), (
        f"no blocking step in ci.yml runs lint-imports: {blocking}"
    )


def test_the_process_document_no_longer_calls_the_gate_work_ahead():
    """§7.1's own preamble: «„Планируется“ — это не „где“, а „нигде“. Такая
    строка не блокирует ничего и не является проверкой». The row said
    «планируется» for as long as there was no configuration. Now there is
    one, and a stale row would tell the next agent the opposite of the
    truth — in the table that agent is instructed to trust."""
    process = PROCESS.read_text(encoding="utf-8")

    row = [
        line
        for line in process.splitlines()
        if line.startswith("|") and "import-linter" in line
    ]

    assert row, "docs/process.md §7.1 no longer has a row for import-linter"
    assert not any("планируется" in line for line in row), (
        f"§7.1 still calls the layer gate work ahead: {row}"
    )
