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

#: A bullet of §3's "Запрещено" naming two layers that may not see each other —
#: «- `sources` импортирует `mergers` или `renderers`». These are what make the
#: three middle folders *independent siblings* rather than three tiers, and in
#: a `layers` contract that is expressed by putting them in one entry: layers
#: forbids sibling-to-sibling imports only within the same entry.
FORBIDDEN_PAIR = re.compile(r"^- `(\w+)` импортирует `(\w+)` или `(\w+)`$", re.MULTILINE)


def _importlinter_config() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["importlinter"]


def _contracts() -> list[dict]:
    return _importlinter_config()["contracts"]


def _architecture_section(start: str, end: str) -> str:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    return text[text.index(start) : text.index(end)]


def _dependency_rules() -> dict[str, set[str]]:
    """§3's «Dependency rules (строго)», read as {layer: layers it may import}."""
    section = _architecture_section("### Dependency rules", "### Запрещено")

    rules = {
        source: set(re.findall(r"`(\w+)`", targets))
        for source, targets in RULE_LINE.findall(section)
    }
    assert rules, "§3's dependency rules no longer parse — the shape of the list changed"
    return rules


def _independent_siblings() -> set[frozenset[str]]:
    """The pairs §3's «Запрещено» forbids in both directions."""
    section = _architecture_section("### Запрещено", "В Python нет enforced")

    pairs = set()
    for source, first, second in FORBIDDEN_PAIR.findall(section):
        pairs.add(frozenset((source, first)))
        pairs.add(frozenset((source, second)))
    assert pairs, "§3's «Запрещено» no longer names a forbidden pair"
    return pairs


def _layers_named_by_architecture() -> set[str]:
    """The layer names §3 writes in its dependency rules, read from §3."""
    names: set[str] = set()
    for source, targets in _dependency_rules().items():
        names.add(source)
        names.update(targets)
    return names


def _layers_contract() -> dict:
    layers = [c for c in _contracts() if c["type"] == "layers"]

    assert len(layers) == 1, f"expected one layers contract, found {len(layers)}"
    return layers[0]


def _tier_of_each_layer() -> dict[str, int]:
    """Position of every layer in the contract, siblings sharing a position.

    `["ui", "core", "sources | mergers | renderers", "domain"]` reads as
    ui=0, core=1, sources=mergers=renderers=2, domain=3.
    """
    tiers: dict[str, int] = {}
    for position, entry in enumerate(_layers_contract()["layers"]):
        for name in (part.strip() for part in entry.split("|")):
            tiers[name] = position
    return tiers


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


def test_the_layers_contract_holds_every_layer_the_document_names():
    """The `layers` contract was guarded by nothing until a mutation run said
    so: deleting it outright, or shrinking it to `layers = ["ui"]`, left all of
    this file green and `lint-imports` at exit 0 — and an import *upwards*,
    `core.peaks -> ui.cli`, then passed both. That is the half of §3 the other
    contract cannot express: `forbidden` watches what `ui` reaches past `core`,
    `layers` is the only thing forbidding the layers below from reaching back
    up at all."""
    assert set(_tier_of_each_layer()) == _layers_named_by_architecture()


def test_every_dependency_rule_points_downwards_in_the_contract():
    """Order, not just membership. `["domain", "core", …]` keeps every name and
    inverts the architecture; this reads each «`A` → `B`» of §3 and asks the
    contract to place A above B."""
    tiers = _tier_of_each_layer()

    for source, targets in _dependency_rules().items():
        for target in targets:
            assert tiers[source] < tiers[target], (
                f"§3 says `{source}` → `{target}`, contract puts {source} at "
                f"{tiers[source]} and {target} at {tiers[target]}"
            )


def test_the_independent_siblings_share_one_position():
    """§3 forbids `sources`, `mergers` and `renderers` from importing each
    other in every direction. A `layers` contract says that by holding them in
    one entry — split across entries, the lower ones become fair game for the
    higher, and three prohibitions of §3 quietly stop being checked."""
    tiers = _tier_of_each_layer()

    for pair in _independent_siblings():
        first, second = sorted(pair)
        assert tiers[first] == tiers[second], (
            f"§3 forbids `{first}` ↔ `{second}`; the contract puts them at "
            f"{tiers[first]} and {tiers[second]}, so one may import the other"
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
    identically in the file and block nothing.

    The `--contract` clause is the reason this asks for more than a prefix. A
    mutation run disarmed the gate while leaving the word `lint-imports`
    literally in place: give the first contract an `id` and write
    `lint-imports --contract layers`, and CI runs one contract, exits 0, and
    never evaluates the adjacency rule this whole file exists for. A test
    matching the head of the line called that a gate. Running *every* contract
    is the property; anything selecting a subset is not this step."""
    blocking = _blocking_steps(CI_WORKFLOW.read_text(encoding="utf-8"))

    gate = [line for line in blocking if line.split() and line.split()[0] == "lint-imports"]

    assert gate, f"no blocking step in ci.yml runs lint-imports: {blocking}"
    assert any("--contract" not in line for line in gate), (
        f"ci.yml only ever runs a subset of the contracts: {gate}"
    )


def _section_71() -> str:
    """§7.1 alone.

    Scoped, because the un-scoped version was satisfied by the wrong table:
    §8 also has a row saying `import-linter` is how `ARCHITECTURE.md` is
    checked, so "a row mentioning import-linter exists" stayed true with §7.1's
    row deleted outright — which is the very state this is meant to forbid."""
    process = PROCESS.read_text(encoding="utf-8")
    return process[process.index("### 7.1") : process.index("### 7.2")]


def test_the_process_document_no_longer_calls_the_gate_work_ahead():
    """§7.1's own preamble: «„Планируется“ — это не „где“, а „нигде“. Такая
    строка не блокирует ничего и не является проверкой». The row said
    «планируется» for as long as there was no configuration. Now there is
    one, and a stale row would tell the next agent the opposite of the
    truth — in the table that agent is instructed to trust."""
    row = [
        line
        for line in _section_71().splitlines()
        if line.startswith("|") and "import-linter" in line
    ]

    assert row, "§7.1 has no row for the layer gate at all"
    assert not any("планируется" in line for line in row), (
        f"§7.1 still calls the layer gate work ahead: {row}"
    )


def test_the_status_paragraph_agrees_with_the_gate_table():
    """The document says the same thing twice, so it can disagree with itself
    in one of them. The opening status paragraph lists the gates that are
    «работой впереди, а не действующей проверкой», and it named the layer gate
    for as long as §7.1 did. Guarded because a mutation run put it back and
    every other test here stayed green: §7.1 would say CI, the fourth paragraph
    of the same file would say not yet, and the reader has no way to tell which
    is current."""
    process = PROCESS.read_text(encoding="utf-8")
    status = process[process.index("Статус:") : process.index("## 0. Принципы")]

    ahead = status[status.index("Не включены") :]

    assert "import-linter" not in ahead, (
        "the status paragraph still lists the layer gate as work ahead, "
        "while §7.1 calls it a CI gate"
    )
