"""`FEATURE_REQUESTS.md` has to agree with the code it describes.

`02_Статус_и_заметки.md` points every reader — and every agent — at
`FEATURE_REQUESTS.md` as the product backlog and calls its statuses reliable.
That sentence is load-bearing: it is the reason a newcomer trusts a `❌` and
stops looking. When the `❌` is wrong, the document does not merely go stale,
it actively sends work at a feature that already shipped.

The rot here is structural rather than random, and knowing its shape is what
makes it checkable. Each section grew by *appending*: a `> **Итерация N ✅**`
blockquote goes in at the top as the work lands, while the original request
block below it — `**Что хотим:**`, `**Статус:**`, `**Что делать:**` — is
frozen at the day the feature was asked for and never revisited. So a section
ends up carrying two statuses that disagree, and the older one is the one a
reader meets last.

What this file checks is deliberately narrow, and the boundary is the point.
It does not judge whether `✅` or `⚠️` is the better word for a half-finished
feature — that is a product judgement and it belongs to a human. It checks the
half a machine can settle: *the document says this is not built, and here is
the file that builds it*. Named artefacts either exist or they do not.

Three guards, not one:

* :func:`test_a_shipped_feature_is_not_declared_unbuilt` — the rule above,
  against the curated evidence in :data:`EVIDENCE`.
* :func:`test_a_sections_heading_and_status_agree` — a section's heading
  marker and its status marker have to be the same one. This needs no
  evidence table, so it is the check that covers every feature, including the
  five whose code nobody has read.
* :func:`test_every_section_declares_a_status` — because the first two read
  status lines and skip what they do not find, so removing the verdict is a
  cheaper way to green them than correcting it. Three sections had no status
  line at all when this was written, and a verdict pushed onto the next line
  renders the same while reading as nothing.

Not this file's job: the paths in every other document. `ARCHITECTURE.md` is
guarded by `tests/test_docs_architecture.py`, and widening that guard to the
rest of the tree is separate, tracked work.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURE_REQUESTS = PROJECT_ROOT / "FEATURE_REQUESTS.md"
STATUS_NOTES = PROJECT_ROOT / "02_Статус_и_заметки.md"

#: The sentence in `02_Статус_и_заметки.md` that sends readers here, and the
#: name it has to carry. A claim of reliability with nothing behind it is how
#: this document earned its reputation the first time; naming the guard in the
#: prose means the reader can check who is keeping the promise.
#: The claim lives on a line of its own, and that is a requirement rather than
#: a layout preference: the bullet above it names the backlog as «фичи #1–#9»,
#: and a range on the same line would read to the check below as a claim that
#: #1 and #9 are code-verified.
RELIABILITY_CLAIM = "Чем сторожатся статусы"
GUARD_NAME = "tests/test_feature_statuses.py"

#: `### #8 🔮 Combat-aware renderer` — the section heading, and the number that
#: identifies the feature.
HEADING = re.compile(r"^###\s+#(\d+)\s+(.*)$")

#: `**Статус:** ❌ не реализовано`. Bold, at the start of a line, because the
#: word also appears mid-sentence in prose that is describing history rather
#: than declaring anything.
#: Up to three leading spaces, which is all Markdown allows before a line
#: keeps its meaning — a fourth makes it an indented code block, and `^\s*`
#: would read such an example as the section's real verdict.
STATUS_LINE = re.compile(r"^ {0,3}(?:>\s*)?\*\*Статус:\*\*\s*(.*)$")

#: Opening or closing fence of a code block, ``` or ~~~.
FENCE = re.compile(r"^ {0,3}(?:```|~~~)")

#: The verdict markers that mean "not built, or not built yet". Reading the
#: marker rather than the sentence is what makes this checkable at all: the
#: wordings vary («не поддерживается», «каркас готов, парсинг таймстемпов
#: нет», «core есть, пайплайн не зовёт, UI нет») and share no vocabulary,
#: while every one of them is introduced by the same emoji. A word list built
#: from today's four sentences would miss tomorrow's fifth.
#:
#: `⚠️` counts alongside `❌` deliberately. Both of the split sections this
#: file was written for — #3 and #7 — used `⚠️`, not `❌`; a rule that only
#: read `❌` would have called them clean.
UNBUILT_MARKERS = ("❌", "⚠️")

#: Wordings that declare a feature unbuilt without an emoji to introduce them.
#: Kept narrow on purpose: prose is full of qualified negatives ("парсинг
#: есть, но не для UI") that are descriptions rather than verdicts, and a rule
#: loose enough to catch those would fire on every honest caveat in the file.
DECLARES_UNBUILT = (
    "не реализовано",
    "не поддерживается",
    "не сделано",
)

#: The way out, and it has to exist. "The module is written but nothing calls
#: it" is a real and common state, and it is honestly described by `⚠️` next
#: to a file that exists — which is exactly the shape this test otherwise
#: rejects. Without an escape the only way to green the check would be to
#: overstate the feature, so the guard would push the document into a *new*
#: lie to stop it telling the old one.
#:
#: Same idea as `(planned)` in `tests/test_docs_architecture.py`: the escape is
#: a written claim, not a silent skip. Marking a status `(частично)` says the
#: author compared it against the code and stands behind the `⚠️`, and the
#: legend in `FEATURE_REQUESTS.md` says so where a reader will meet it.
PARTIAL_ESCAPE = "(частично)"

#: `✅` in a heading is the section's own claim that the feature shipped.
DECLARES_BUILT = "✅"

#: Every verdict marker the legend defines. A status and a heading are
#: compared through these rather than through the sentences around them,
#: because the sentences are free prose and the markers are the vocabulary the
#: document actually commits to.
MARKERS = ("✅", "⚠️", "❌", "🅿️", "📋", "🔮")


#: Line comment markers, by file type. Only the two this table actually names
#: — a general comment parser would be a lie of a different kind, since it
#: cannot see string literals or block comments either.
COMMENT_MARKERS = {".py": "#", ".qml": "//"}


def _live_text(target: Path) -> str:
    """The file with its commented-out lines dropped.

    A plain substring search over the raw file counts code that has been
    switched off. Commenting out the registry line in `renderers/__init__.py`
    takes the combat-aware renderer out of reach of every caller, and the
    string `"combat-aware"` is still sitting there in the comment — so the
    evidence would keep vouching for a feature the user can no longer get.
    That is the exact failure this class exists to prevent, one level down.

    Whole-line comments only, and the limit is worth naming rather than
    hiding: a trailing comment on a live line, a string literal, and a
    docstring all still count. Closing those means parsing each language, and
    a curated table of a dozen artefacts does not earn a parser.
    """
    marker = COMMENT_MARKERS.get(target.suffix)
    text = target.read_text(encoding="utf-8")
    if marker is None:
        return text
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith(marker)
    )


class Artifact:
    """One file, and a string that has to be inside it.

    The string matters as much as the path. `renderers/__init__.py` exists
    whether or not it registers the combat-aware renderer, so a path-only
    check would have gone green through the whole period this test exists to
    end. The symbol is what makes the artefact evidence of the *feature*
    rather than evidence of the file.

    What it is not, and the limit is worth stating rather than leaving for
    someone to discover: presence is not wiring. `SegmentJob` can exist while
    nothing constructs one. Naming a call site rather than a bare name buys
    part of the distance — an import no longer vouches for a deleted call —
    but only running the feature would close it, and that would mean this
    guard importing PySide6 and booting Qt to read a Markdown file. It is a
    documentation guard: it settles "the document says this does not exist,
    and here is the thing", which is what the card asked of it, and it does
    not certify that a feature works. The suites that do that live beside it.
    Reaching the rest is filed separately rather than smuggled in here.
    """

    def __init__(self, path: str, symbol: str, why: str) -> None:
        self.path = path
        self.symbol = symbol
        self.why = why

    def __repr__(self) -> str:  # pragma: no cover - test failure output only
        return f"{self.path} :: {self.symbol}"

    def present(self) -> bool:
        target = PROJECT_ROOT / self.path
        if not target.is_file():
            return False
        return self.symbol in _live_text(target)


#: Feature number → the artefacts that make it real, each with the reason it
#: counts. Only features whose code has actually been read are in here.
#:
#: The omissions are deliberate and worth naming: #1, #2, #5, #6 and #9 carry
#: no entry because nobody has verified their code against their status, and
#: inventing evidence for them would put this file in exactly the business it
#: is meant to police. They are still covered by
#: :func:`test_no_section_declares_both_done_and_undone`, which needs no
#: evidence to run.
EVIDENCE: dict[int, tuple[Artifact, ...]] = {
    3: (
        Artifact(
            "core/timeline_window.py",
            "def build_window(",
            "the absolute time window the source rows are placed on",
        ),
        Artifact(
            "ui/qml/timeline/TimelineRuler.qml",
            "_wallClock",
            "the ruler prints wall-clock hours, not relative minutes",
        ),
        Artifact(
            "sources/game_log/combat_dump.py",
            "class CombatDumpSource(",
            "`Бой N.txt` has a parser",
        ),
        Artifact(
            "core/pipeline.py",
            "game_log=game_log_entries",
            "the parsed dumps reach the Timeline instead of an empty list",
        ),
        # The line above is the CLI path. #3 is about the on-screen timeline,
        # and the GUI reaches the dumps by its own route — so evidence taken
        # only from `core/pipeline.py` would keep endorsing the ✅ after the
        # screen stopped placing combats at all.
        Artifact(
            "ui/models/session.py",
            "meta = parse_combat_file(",
            "the GUI places combats on the axis, not only the merge does",
        ),
    ),
    4: (
        Artifact(
            "core/file_matchers.py",
            "def detect_craig_segments(",
            "discovery descends into `craig-*` / `крэйг-*` subfolders",
        ),
        Artifact(
            "core/file_matchers.py",
            "class CraigSegment:",
            "a segment is a modelled thing, not a bare path",
        ),
        Artifact(
            "core/file_matchers.py",
            "def match_speaker(",
            "the same player across two archives collapses to one row",
        ),
        # Discovery is only iteration 4a. The heading and the status both
        # claim 4b — per-segment ASR and per-segment peaks — and with the
        # three above alone that half of the claim had no artefact at all.
        Artifact(
            "ui/engines/asr_worker.py",
            "class SegmentJob:",
            "4b: ASR runs per segment, not only on the primary one",
        ),
        Artifact(
            "ui/engines/peaks_worker.py",
            "peaksReady = Signal(int, int, list)",
            "4b: peaks are reported per (row, segment), not per row",
        ),
    ),
    7: (
        Artifact(
            "core/chunking.py",
            "class ChunkingOptions:",
            "the chunker's parameters are a contract",
        ),
        Artifact(
            # The call site, not the name. `from core.chunking import
            # chunk_text_file` sits at the top of the same file, so the bare
            # name would keep passing with the whole post-step deleted.
            "core/pipeline.py",
            "chunks_dir = chunk_text_file(",
            "the pipeline calls the chunker; the status line said it does not",
        ),
        Artifact(
            "ui/qml/screens/SettingsScreen.qml",
            "Чанки для LLM",
            "the UI controls exist; the status line says there are none",
        ),
        # The controls existing is not the same as their values arriving. The
        # GUI does not reach the chunker through `core.pipeline.run` at all —
        # it runs its own post-step in `_maybe_chunk_output`, which is the
        # duplication tracked separately on the board. So the CLI call site
        # above says nothing about what feature #7 actually describes: a
        # setting that does something when you use it.
        Artifact(
            "ui/engines/pipeline_controller.py",
            "dest = chunk_text_file(",
            "the GUI's own chunk step, the one those controls feed",
        ),
    ),
    8: (
        Artifact(
            "renderers/combat_aware.py",
            "class CombatAwareRenderer(",
            "the renderer the status line calls unwritten",
        ),
        Artifact(
            "renderers/__init__.py",
            '"combat-aware"',
            "it is registered, so the pipeline can reach it",
        ),
        Artifact(
            # Again the lookup rather than the import on line 37.
            "ui/engines/merger_worker.py",
            "RENDERERS.get(",
            "the worker resolves the renderer through the registry",
        ),
        Artifact(
            "ui/qml/screens/SettingsScreen.qml",
            "С разметкой боёв",
            "the user can actually pick it",
        ),
    ),
}


class Section:
    """One `### #N …` block: its number, where it starts, and what is in it."""

    def __init__(self, feature: int, line: int, heading: str) -> None:
        self.feature = feature
        self.line = line
        self.heading = heading
        self.body: list[str] = []

    def __repr__(self) -> str:  # pragma: no cover - test failure output only
        return f"#{self.feature} (line {self.line}): {self.heading.strip()}"


def _sections(text: str) -> list[Section]:
    """Split the document into `#N` sections, in the order they appear.

    A section runs to the next `###` heading, so the `## 🔮 Future` divider in
    the middle of the file does not truncate it — #9 and #8 live below that
    divider and are sections like any other.

    A *list*, not a dict keyed on the feature number, and that is the point: a
    section copied or moved without deleting the original leaves two blocks
    with the same number, and keyed insertion would silently drop the first.
    The stale copy would stay on the page, contradicting the surviving one,
    while every check here read only the last. Kept as a list, both copies are
    checked and :func:`test_every_feature_section_is_found` reports the
    duplicate.
    """
    found: list[Section] = []
    current: Section | None = None
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            # A fenced block is an example, not a claim. The legend added to
            # `FEATURE_REQUESTS.md` documents how to write a status line, so
            # the first person to show one in a code block would otherwise
            # hand this parser a verdict — and could then delete the section's
            # real status without any check noticing.
            continue
        heading = HEADING.match(line)
        if heading:
            current = Section(int(heading.group(1)), number, heading.group(2))
            found.append(current)
        elif line.startswith("### "):
            # Any other `###` ends the block rather than being swallowed by
            # it. Without this a feature that lost its own status would
            # borrow the verdict of whatever `###` section came next and read
            # as compliant. `## …` does not close anything: the
            # `## 🔮 Future` divider sits between two features, and treating
            # it as a boundary would truncate the ones below it.
            current = None
        elif current is not None:
            current.body.append(line)
    return found


def _marker(text: str) -> str | None:
    """The first legend marker in a string, or `None`.

    Scanned in the order the markers appear in the text rather than in
    :data:`MARKERS`, so a status that mentions a second marker later in the
    sentence still reports the one it leads with.
    """
    positions = [(text.index(m), m) for m in MARKERS if m in text]
    return min(positions)[1] if positions else None


def _status_verdicts(body: list[str]) -> list[str]:
    """The raw text of every `**Статус:**` line in a section."""
    return [
        status.group(1).strip()
        for line in body
        if (status := STATUS_LINE.match(line)) is not None
    ]


def _unbuilt_declarations(body: list[str]) -> list[str]:
    """Status lines in a section body that declare the feature unbuilt.

    Only a `**Статус:**` line is a verdict. The same markers and the same
    words appear in the history blockquotes above it — «Что НЕ сделано
    (итерация 3b, future)» is a note about the past, not a claim about today —
    and reading those as verdicts would make every honest caveat in the file
    fire this check.
    """
    declarations = []
    for line in body:
        status = STATUS_LINE.match(line)
        if not status:
            continue
        verdict = status.group(1)
        # The escape belongs to `⚠️` and to nothing else. The legend grants it
        # for "written but not wired", which is what `⚠️` says; on a `❌` it
        # would let «не реализовано (частично)» wave a shipped feature
        # through — the exact claim this file exists to refuse.
        leading = _marker(verdict)
        if PARTIAL_ESCAPE in verdict and leading == "⚠️":
            continue
        # The *leading* marker is the verdict, matching what :func:`_marker`
        # already promises and what the heading comparison already does.
        # Searching the whole string would read «✅ готово; прежний статус ⚠️
        # частично» as a claim that the feature is unbuilt, and fail an
        # honest historical note. Wordings are consulted only when there is
        # no marker to go by.
        if leading in UNBUILT_MARKERS or (
            leading is None and any(word in verdict for word in DECLARES_UNBUILT)
        ):
            declarations.append(verdict.strip())
    return declarations


def _document() -> list[Section]:
    return _sections(FEATURE_REQUESTS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("feature", sorted(EVIDENCE))
def test_a_shipped_feature_is_not_declared_unbuilt(feature):
    """The rule the whole file exists for.

    Feature #8 sat at `**Статус:** ❌ не реализовано` while
    `renderers/combat_aware.py` shipped, was registered, was wired to a
    dropdown reading «С разметкой боёв», and had 28 tests on it. The document
    additionally blamed a blocker — "требует #3" — that had been cleared in
    the same file it pointed at.
    """
    sections = [s for s in _document() if s.feature == feature]
    assert sections, f"FEATURE_REQUESTS.md has no section for #{feature}"

    missing = [artifact for artifact in EVIDENCE[feature] if not artifact.present()]
    assert not missing, (
        f"the evidence for #{feature} has moved; this table is now checking nothing:\n"
        + "\n".join(f"  {artifact} — {artifact.why}" for artifact in missing)
    )

    declarations = [d for s in sections for d in _unbuilt_declarations(s.body)]
    assert not declarations, (
        f"#{feature} is declared unbuilt while every artefact of it exists.\n"
        f"the document says:\n"
        + "\n".join(f"  **Статус:** {line}" for line in declarations)
        + "\nthe tree says:\n"
        + "\n".join(f"  {artifact} — {artifact.why}" for artifact in EVIDENCE[feature])
    )


def test_a_sections_heading_and_status_agree():
    """A section may not claim two different things at once.

    #3 carried `✅` in its heading and `⚠️ каркас готов, парсинг таймстемпов
    нет` below it; #4 and #7 had the identical split. A reader who scrolled
    met the stale half last.

    Markers are compared for equality rather than only catching `✅` over
    `❌`, and that is the whole difference between this check and a decorative
    one: keyed on `✅` alone, renaming a heading to `🔮` would lift a section
    out of the check entirely, and for the features with no entry in
    :data:`EVIDENCE` nothing else is watching them at all. Equality has no
    such escape — every rename still has to match the status below it.

    This needs no evidence table, so unlike
    :func:`test_a_shipped_feature_is_not_declared_unbuilt` it really does
    speak for every feature in the document.

    A heading with no marker at all is a failure here rather than a skip.
    Comparing two things means having two things: treating a missing marker as
    "nothing to compare" would let a section escape by deleting precisely the
    mark being guarded, which is cheaper than any of the edits this catches.
    """
    contradictions = []
    for section in _document():
        claimed = _marker(section.heading)
        if claimed is None:
            contradictions.append(
                f"{section!r}: heading carries no status marker, so there is "
                f"nothing to compare its status against"
            )
            continue
        for verdict in _status_verdicts(section.body):
            declared = _marker(verdict)
            if declared is not None and claimed != declared:
                contradictions.append(
                    f"{section!r}: heading says «{claimed}», "
                    f"status says «{declared}» in «{verdict}»"
                )

    assert not contradictions, "sections that contradict themselves:\n" + "\n".join(
        contradictions
    )


def test_the_reliability_claim_names_its_guard_and_its_limits():
    """`02_Статус_и_заметки.md` may promise reliable statuses only while
    something is keeping the promise, and only as far as it is kept.

    That sentence is what makes the backlog authoritative for anyone arriving
    without context. Naming this file next to it turns an assurance into a
    reference — the reader can see who is checking.

    It also has to name *which* features are checked against code, and that is
    not decoration: the guard reads the tree for the four in :data:`EVIDENCE`
    and, for the other five, only checks that a section does not contradict
    itself. Two stale-but-agreeing markers pass. A blanket «статусы
    достоверны» over all nine would be the same kind of overclaim this whole
    file exists to remove, one level up — so the sentence is pinned to the
    table, and adding a feature to :data:`EVIDENCE` without saying so here
    fails.
    """
    text = STATUS_NOTES.read_text(encoding="utf-8")

    assert RELIABILITY_CLAIM in text, (
        f"{STATUS_NOTES.name} no longer claims the statuses are reliable — if that "
        "claim was dropped on purpose, this test goes with it"
    )
    claim_line = next(line for line in text.splitlines() if RELIABILITY_CLAIM in line)
    assert GUARD_NAME in claim_line, (
        f"{STATUS_NOTES.name} claims «{RELIABILITY_CLAIM}» without naming what "
        f"checks it; expected {GUARD_NAME} on the same line, got:\n  {claim_line}"
    )
    # `f"#{n}" in line` would accept `#30` as a mention of `#3`, letting the
    # sentence name features that are not the ones being checked.
    named = {int(n) for n in re.findall(r"#(\d+)", claim_line)}
    # Both directions. Naming every checked feature stops the sentence from
    # understating the guard; refusing an unchecked one stops it overstating —
    # and overstating is the failure this whole file exists to remove. A claim
    # that #9 is code-verified would be the old lie in a new place.
    assert named == set(EVIDENCE), (
        f"{STATUS_NOTES.name} must name exactly the features checked against the "
        f"code.\n  claims: {sorted(named) or 'none'}\n  checked: {sorted(EVIDENCE)}\n"
        f"  line: {claim_line}"
    )


def test_every_feature_section_is_found():
    """A guard on the guard.

    Both checks above iterate whatever :func:`_sections` returns, so a parser
    that quietly stopped matching headings would leave them green while
    reading nothing — the failure mode that makes a test worse than no test.

    The features are required to be a gapless run from #1 rather than the
    literal nine there are today: pinning the count would turn adding #10 into
    a failing test, and a guard that punishes growth gets deleted.

    Duplicates fail here rather than being tolerated. A section copied or
    moved without deleting the original leaves two blocks claiming the same
    number, and the stale one goes on contradicting the live one in front of
    every reader.
    """
    sections = _document()
    numbers = [section.feature for section in sections]

    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert not duplicates, (
        f"these feature numbers have more than one section: {duplicates}\n"
        + "\n".join(f"  {s!r}" for s in sections if s.feature in duplicates)
    )
    assert len(sections) >= 9, f"expected at least nine features, found {sorted(numbers)}"
    assert sorted(numbers) == list(range(1, len(sections) + 1)), (
        f"feature numbers are not a gapless run from 1: {sorted(numbers)}"
    )
    assert all(section.body for section in sections), "a section came back empty"


def test_every_section_declares_a_status():
    """Silence is the cheapest way to green the other two checks.

    Both of them read `**Статус:**` lines and iterate only the ones they find,
    so a section with no status line at all is invisible to them — and
    deleting a line is easier than correcting it. #1, #5 and #9 had no status
    line, which meant
    :func:`test_a_sections_heading_and_status_agree` was quietly saying
    nothing about a third of the backlog while its own docstring claimed it
    spoke for all nine.

    `(частично)` is the escape hatch, and it is the *only* one. It is a
    written claim that someone compared the status against the code; an
    absent line is a claim that nobody did.

    The verdict has to be on the line, and carry a marker. `**Статус:**` with
    the word on the *next* line renders identically in Markdown — a soft break
    — while leaving the regex an empty capture, which reads to every check
    above as "nothing declared here". One newline would otherwise buy the same
    exemption as deleting the line, which is the hole this test exists to
    close.
    """
    problems = []
    for section in _document():
        verdicts = _status_verdicts(section.body)
        if not verdicts:
            problems.append(f"{section!r}: no **Статус:** line")
            continue
        for verdict in verdicts:
            if not verdict:
                problems.append(
                    f"{section!r}: **Статус:** with an empty verdict — the word "
                    "belongs on the same line"
                )
            elif _marker(verdict) is None:
                problems.append(
                    f"{section!r}: «{verdict}» carries no status marker; "
                    f"expected one of {' '.join(MARKERS)}"
                )

    assert not problems, (
        "every section has to declare a status the checks above can read:\n"
        + "\n".join(problems)
    )


def test_the_status_extractor_reads_a_declaration():
    """And that it tells a verdict from prose about one.

    `**Статус:**` is the only line that declares; the same words appear in
    history blockquotes and in caveats, and reading those as verdicts would
    make every honest «что НЕ сделано» note fire this test.
    """
    assert _unbuilt_declarations(["**Статус:** ❌ не реализовано"]) == [
        "❌ не реализовано"
    ]
    # The two wordings that share no vocabulary with each other and no
    # vocabulary with `❌ не реализовано` — only the marker connects them.
    assert _unbuilt_declarations(
        ["**Статус:** ⚠️ каркас готов, парсинг таймстемпов нет"]
    ) == ["⚠️ каркас готов, парсинг таймстемпов нет"]
    assert _unbuilt_declarations(
        ["**Статус:** ⚠️ core есть, пайплайн не зовёт, UI нет"]
    ) == ["⚠️ core есть, пайплайн не зовёт, UI нет"]
    # A verdict with no emoji is still a verdict.
    assert _unbuilt_declarations(["**Статус:** не поддерживается"]) == [
        "не поддерживается"
    ]
    assert _unbuilt_declarations(["**Статус:** ✅ готово"]) == []
    assert _unbuilt_declarations(["> **Что НЕ сделано:** ❌ отложено"]) == []
    assert _unbuilt_declarations(["прежде было ❌ не реализовано, теперь нет"]) == []


def test_a_partial_status_may_stand_when_it_says_so():
    """Otherwise the only way to green this check is to overstate the feature.

    "The module is written, nothing calls it" is a real state and `⚠️` is the
    honest word for it. The escape makes that an explicit, written claim
    instead of a silent hole — and it is written where a reader meets it, not
    only here."""
    assert _unbuilt_declarations(
        ["**Статус:** ⚠️ core есть, пайплайн не зовёт (частично)"]
    ) == []
    assert _unbuilt_declarations(["**Статус:** ⚠️ core есть, пайплайн не зовёт"]) == [
        "⚠️ core есть, пайплайн не зовёт"
    ]


def test_switched_off_code_is_not_evidence(tmp_path):
    """Commenting out the registry line takes the renderer out of every
    caller's reach while leaving the string in the file. A raw substring
    search keeps vouching for a feature nobody can select any more."""
    registry = tmp_path / "__init__.py"
    registry.write_text('    "combat-aware": CombatAwareRenderer,\n', encoding="utf-8")
    assert '"combat-aware"' in _live_text(registry)

    registry.write_text('    # "combat-aware": CombatAwareRenderer,\n', encoding="utf-8")
    assert '"combat-aware"' not in _live_text(registry)

    screen = tmp_path / "Screen.qml"
    screen.write_text('    // text: "С разметкой боёв"\n', encoding="utf-8")
    assert "С разметкой боёв" not in _live_text(screen)

    # A file type with no comment syntax in the table is read whole rather
    # than silently half-read.
    plain = tmp_path / "notes.md"
    plain.write_text("# heading stays\n", encoding="utf-8")
    assert "heading stays" in _live_text(plain)


def test_the_escape_is_documented_where_readers_meet_it():
    """A convention only this file knows is a convention nobody follows. The
    next person to write a `⚠️` status finds the test red and no way out
    unless the document itself explains the escape."""
    text = FEATURE_REQUESTS.read_text(encoding="utf-8")

    assert PARTIAL_ESCAPE in text, (
        f"{FEATURE_REQUESTS.name} never explains {PARTIAL_ESCAPE}, so the only "
        "way past this guard is to overstate a feature"
    )
    assert GUARD_NAME in text, (
        f"{FEATURE_REQUESTS.name} does not name {GUARD_NAME}, so a reader hitting "
        "the guard cannot find what is checking them"
    )


def test_the_heading_parser_keeps_sections_apart():
    """Sections end at the next `###`, not at the `## 🔮 Future` divider that
    sits between #7 and #9 — otherwise the two features below it would inherit
    each other's bodies, and #8's status would be read out of #9's section."""
    document = "\n".join(
        [
            "### #7 ✅ Chunker",
            "**Статус:** ✅ готово",
            "## 🔮 Future",
            "### #8 🔮 Renderer",
            "**Статус:** ❌ не реализовано",
        ]
    )
    sections = _sections(document)

    assert [section.feature for section in sections] == [7, 8]
    assert _unbuilt_declarations(sections[0].body) == []
    assert _unbuilt_declarations(sections[1].body) == ["❌ не реализовано"]


def test_an_example_status_is_not_a_status():
    """The legend documents how to write a status line, so the first person to
    illustrate one in a code block would hand this parser a verdict — and
    could then delete the section's real status with nothing noticing."""
    fenced = "\n".join(
        ["### #3 ✅ Ось", "Пишется так:", "```", "**Статус:** ✅ готово", "```"]
    )
    indented = "\n".join(["### #3 ✅ Ось", "Пишется так:", "    **Статус:** ✅ готово"])

    assert _status_verdicts(_sections(fenced)[0].body) == []
    assert _status_verdicts(_sections(indented)[0].body) == []
    # …while a real one, at the margin, still reads.
    real = "\n".join(["### #3 ✅ Ось", "**Статус:** ✅ готово"])
    assert _status_verdicts(_sections(real)[0].body) == ["✅ готово"]


def test_a_non_feature_heading_ends_the_block():
    """Otherwise a feature that lost its own status borrows the next section's.

    `## …` still does not close a block — the `## 🔮 Future` divider sits
    between two features — but any other `###` does, exactly as the parser's
    docstring has always claimed."""
    document = "\n".join(
        [
            "### #3 ✅ Ось",
            "какой-то текст",
            "### Приложение",
            "**Статус:** ✅ готово",
        ]
    )
    sections = _sections(document)

    assert [section.feature for section in sections] == [3]
    assert _status_verdicts(sections[0].body) == [], (
        "#3 has no status of its own and must not inherit the appendix's"
    )


def test_a_historical_marker_later_in_the_line_is_not_the_verdict():
    """`_marker` calls the leading marker authoritative; this classification
    has to agree with it, or an honest note about what the status used to be
    fails the evidence guard."""
    assert _unbuilt_declarations(
        ["**Статус:** ✅ готово; прежний статус ⚠️ частично"]
    ) == []
    assert _unbuilt_declarations(["**Статус:** ⚠️ ядро есть, UI нет"]) == [
        "⚠️ ядро есть, UI нет"
    ]


def test_a_duplicated_section_is_kept_rather_than_overwritten():
    """A section copied without deleting the original claims a number twice.
    Keyed on the number, the first copy would vanish from every check while
    staying on the page, contradicting the one that survived."""
    document = "\n".join(
        [
            "### #3 ✅ Первая",
            "**Статус:** ✅ готово",
            "### #3 ❌ Забытая копия",
            "**Статус:** ❌ не реализовано",
        ]
    )
    sections = _sections(document)

    assert [section.feature for section in sections] == [3, 3]
    assert _unbuilt_declarations(sections[1].body) == ["❌ не реализовано"]


def test_the_marker_reader_takes_the_leading_verdict():
    """Comparing headings to statuses turns on reading one marker per string,
    and the one it leads with — a status that goes on to mention another
    marker in passing still declares the first."""
    assert _marker("### #8 ✅ Combat-aware renderer") == "✅"
    assert _marker("🅿️ запаркована — код жив") == "🅿️"
    assert _marker("⚠️ core есть, было ✅ до правки") == "⚠️"
    assert _marker("анализ готов, реализация в три этапа") is None


def test_a_verdict_on_the_next_line_is_not_a_verdict():
    """Markdown renders it as one line, so it looks like a status and reads as
    an empty one. Left alone, a single newline exempts a section from both
    substantive checks — cheaper than the deletion this guard already
    catches."""
    split = ["**Статус:**", "❌ не реализовано"]

    assert _status_verdicts(split) == [""]
    assert _unbuilt_declarations(split) == []
    assert _marker("") is None
