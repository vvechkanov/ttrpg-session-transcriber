"""§5 has to look for approval where approval actually arrives.

The review loop in `docs/process.md` §5 decides one thing: has the current
iteration been reviewed yet? Get that wrong in the safe direction and the
night ends with a green, approved PR still sitting in «На ревью» — which is
what happened, repeatedly, and is the reason this file exists.

The rule §5 carried named two signs. One of them, a thumbs-up reaction on the
PR, is invisible to the agent that has to act on it: the cloud runner reaches
GitHub only through the MCP tools, and those expose no reactions endpoint at
all. A sign the reader cannot observe is worse than a missing one — the agent
waits for it, and waiting looks like working.

Codex's own boilerplate advertises that reaction on every message it posts, so
the pull back towards it is permanent and comes from outside this repository.
That is why the ban below is on the whole word family rather than on the one
codepoint, and why it covers the document rather than the section.

These tests check the half a machine can check: that §5 names both signs the
agent *can* observe, that it attaches each sign to the right channel, and that
nothing in the document sends the reader back to reactions. They deliberately
do not judge the prose around those facts — how the rule is explained is for
review; which signal it points at, and which way round, is for a test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESS = PROJECT_ROOT / "docs" / "process.md"


def phrase(text: str) -> re.Pattern[str]:
    """A phrase matcher tolerant of line wrapping, and of nothing else.

    The document is hard-wrapped, so a sentence this file pins can be re-flowed
    by an edit that changes no words. Matching runs of whitespace as one keeps
    that from being a false failure — while still holding the word *order*,
    which is the whole point of pinning a phrase rather than a token.
    """
    return re.compile(r"\s+".join(re.escape(word) for word in text.split()))


#: §5 runs from its own heading to the next top-level one. Anchored on the
#: number rather than the title so that renaming the section is a visible
#: failure here instead of a silently empty match.
SECTION_5 = re.compile(r"^## 5\..*?(?=^## 6\.)", re.MULTILINE | re.DOTALL)

#: The two channels, each as (opening phrase, where the paragraph ends, the
#: call it must prescribe). Checking the call inside its own paragraph is what
#: makes this a guard rather than a bag of tokens: both method names appear in
#: §5 either way round, so a document that swapped them — findings arrive as
#: comments, approval as a review — passes any test that only asks whether
#: each name occurs somewhere.
#:
#: Matched against the *fenced call*, not against any mention. The approval
#: paragraph rightly explains that polling `get_reviews` alone never converges,
#: so a paragraph-wide ban on the other name would forbid the sentence that
#: makes the rule make sense. What must not be swapped is the instruction.
CHANNELS = {
    "findings": ("**Есть замечания", "**Сказать нечего", "get_reviews"),
    "approval": ("**Сказать нечего", "**SHA в этой строке", "get_comments"),
}

#: How §5 writes a call the agent is meant to make.
PRESCRIBED_CALL = re.compile(r"pull_request_read method=(\w+)")

#: Facts §5 has to state, as phrases rather than tokens, because for each of
#: these the inverted document contains the same words.
#:
#: `начинается с` on its own is satisfied by "на равенство, а не через
#: «начинается с»" — the exact rule reversed. Same for the `APPROVED` claim.
#: Each entry carries the reason it is load-bearing.
REQUIRED_CLAIMS = {
    "the sign a review carries": (
        phrase("commit_id"),
        "a review is only evidence about the commit it names",
    ),
    "the line the comment carries": (
        phrase("Reviewed commit"),
        "the comment is only evidence if the reader matches its sha line",
    ),
    "how long that sha is": (
        phrase("префикс в 10 символов"),
        "the comment carries a 10-character prefix, and a reader who assumes "
        "a full sha compares two things that can never be equal",
    ),
    "which way that sha is compared": (
        phrase("через «начинается с», а не на равенство"),
        "prefix matching is the whole point, and the reversed sentence "
        "contains all the same words — so the order is what has to be pinned",
    ),
    "whose messages count": (
        phrase("chatgpt-codex-connector[bot]"),
        "an unfiltered search matches a human comment quoting the same line, "
        "which happened on PR #19 — the author filter is not decorative",
    ),
    "that approval never arrives as a state": (
        phrase("`APPROVED` Codex не выставляет"),
        "polling for an APPROVED review waits for something the bot has "
        "never once emitted",
    ),
    "where HEAD comes from": (
        phrase("method=get → head.sha"),
        "§5 compares everything against HEAD; without this it names the "
        "comparison and not the operand",
    ),
    "how the pages are walked": (
        phrase("`page` и `perPage`"),
        "old reviews fall off the first page and the card sticks in «На "
        "ревью» forever",
    ),
    "how to ask when nothing arrives": (
        phrase("@codex review"),
        "otherwise the loop's only exit is a promise about a third-party "
        "service",
    ),
    "that step 10.1 itself names both channels": (
        phrase("ревью **или одобрительного комментария**"),
        "the numbered list is what the agent executes top-down; leaving "
        "«дождаться ревью» there reproduces the exact wording that caused "
        "the bug, whatever the prose eighty lines below says",
    ),
    "why the reads left `gh`": (
        phrase("закрыт политикой egress"),
        "§5 carries two tool vocabularies; without the reason, the next "
        "editor reads it as an unfinished migration and finishes it the "
        "wrong way",
    ),
    "how long to wait before asking": (
        phrase("ждать до 20 минут"),
        "an unbounded wait and a wait in the wrong unit look identical to a "
        "reader, and both spend the night",
    ),
    "that asking is bounded per commit, not per run": (
        phrase("один раз на HEAD-коммит"),
        "the card outlives the night: a per-run bound lets the next run "
        "re-enter the same iteration at the same HEAD and spend another "
        "forty minutes on a PR that is simply silent",
    ),
    "that the invocation carries the commit it asks about": (
        phrase("@codex review (HEAD:"),
        "a PR comment has no commit attached, so a bare invocation cannot be "
        "told apart from last night's — the per-commit bound is unenforceable "
        "unless the sha is written into the call itself",
    ),
    "that the lookup matches the call, not just the sha": (
        phrase("не один SHA"),
        "the agent posts other things carrying the sha — §9's «СОСТОЯНИЕ:» "
        "names the branch commit in its text — and matching the sha alone "
        "would read one of those as an invocation that never happened, "
        "costing the silent PR its only call",
    ),
}

#: What the process document must not send the reader after, anywhere. The
#: cloud agent has no way to read any of it: `api.github.com` is refused by
#: the egress policy, and the GitHub MCP surface has no reactions call.
#:
#: `реакц` catches the whole Russian word family, and that breadth is the
#: point. Banning only the emoji bans a codepoint, not a signal: «Codex может
#: также поставить реакцию — это тоже одобрение» reintroduces the exact defect
#: with the emoji nowhere in sight.
#:
#: Matched case-folded, because a sentence or heading opening with «Реакция»
#: or "Reaction" is the most natural way to write the rule back in — and a
#: case-sensitive substring check would wave it straight through.
#:
#: Banned across the whole document rather than only §5 for the same reason.
#: §6 step 3 sends the night agent into this very rule («для каждой карточки в
#: «На ревью» выполнить §5, шаг 10»), and §6 is read first. A reaction rule
#: parked in §6 would be obeyed just as readily, and the failure it causes —
#: approved PRs sleeping in «На ревью» — would come back with this file green.
UNOBSERVABLE_SIGNS = {
    "👍": "the reaction itself, which no available tool can read",
    "реакц": "any rule phrased around a reaction, emoji or not",
    "reaction": "the same rule reached for in English, including /reactions",
}


@pytest.fixture(scope="module")
def process_doc() -> str:
    """The whole document, for the bans that are not section-scoped."""
    return PROCESS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def section_5(process_doc: str) -> str:
    """§5 as text — read from the document, never restated here.

    Hard-coding the section body would make this file its own authority: the
    test would keep passing after §5 said something else entirely.
    """
    match = SECTION_5.search(process_doc)
    assert match, "docs/process.md has no §5 between the §5 and §6 headings"
    return match.group(0)


def test_the_extractor_stops_where_the_section_does(section_5: str) -> None:
    """The regex reads §5, not the rest of the file.

    Guarding the empty match is the obvious half and the fixture does it. This
    is the other half: drop the lookahead and the match runs to end of file,
    every assertion below still passes, and the guard silently searches the
    whole document while claiming to search one section.
    """
    assert "## 6." not in section_5, "§5 ran past its own end"
    assert "**Аудит.**" not in section_5, "§5 swallowed §6's audit step"


def test_section_5_is_actually_there(section_5: str) -> None:
    """Non-vacuity — load-bearing, not a formality.

    Two of the tests below are bans, and `token not in ""` is true of the
    empty string. They are only meaningful because this runs beside them.

    The floor sits just under the real length rather than at a round number:
    §5 is 205 lines, and a floor of 50 would let it lose three quarters of
    itself — including every paragraph this guard exists to protect — while
    staying green.
    """
    assert "Цикл ревью" in section_5, "§5 no longer contains the review loop"
    assert len(section_5.splitlines()) > 190, "§5 lost a substantial part"


@pytest.mark.parametrize(("channel", "spec"), sorted(CHANNELS.items()))
def test_each_channel_prescribes_its_own_call(
    section_5: str, channel: str, spec: tuple[str, str, str]
) -> None:
    """The right call sits in the right paragraph, not merely somewhere.

    Both method names appear in §5 whichever way round the document has them,
    so a presence check cannot tell the rule from its inversion. This can: it
    reads the call each paragraph actually prescribes.
    """
    opening, closing, expected = spec
    start = section_5.find(opening)
    assert start != -1, f"§5 no longer opens the {channel} channel with {opening!r}"
    end = section_5.find(closing, start + 1)
    assert end != -1, f"the {channel} paragraph no longer ends at {closing!r}"

    prescribed = PRESCRIBED_CALL.findall(section_5[start:end])
    assert prescribed == [expected], (
        f"the {channel} paragraph prescribes {prescribed or 'no call'}, "
        f"expected exactly ['{expected}'] — the two channels look swapped, "
        "which sends the agent to the one that stays silent for this case"
    )


@pytest.mark.parametrize(
    ("claim", "pattern", "why"),
    [(name, pattern, why) for name, (pattern, why) in REQUIRED_CLAIMS.items()],
)
def test_section_5_states_the_claims_the_agent_acts_on(
    section_5: str, claim: str, pattern: re.Pattern[str], why: str
) -> None:
    """Each fact the loop depends on is stated, and stated the right way."""
    assert pattern.search(section_5), f"§5 does not state {claim}: {why}"


@pytest.mark.parametrize(("token", "why"), sorted(UNOBSERVABLE_SIGNS.items()))
def test_the_document_does_not_send_the_reader_after_reactions(
    process_doc: str, token: str, why: str
) -> None:
    """No section depends on a signal the cloud agent cannot see."""
    assert token.casefold() not in process_doc.casefold(), (
        f"docs/process.md still mentions {token!r}: {why}. "
        "A sign the agent cannot observe makes it wait instead of act."
    )
