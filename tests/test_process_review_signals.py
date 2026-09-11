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

#: §6 likewise. The audit step lives here, and it is the half of this file's
#: subject that decides whether the night runs at all.
SECTION_6 = re.compile(r"^## 6\..*?(?=^## 7\.)", re.MULTILINE | re.DOTALL)

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
    "approval": ("**Сказать нечего", "Искать надо единственный", "get_comments"),
}

#: The approval region above stops at the sentence after its fence, not at
#: the end of the rule it opens. That is narrower than it looks like it
#: should be, and deliberately so: the assertion is an *exact* list of
#: prescribed calls, so every paragraph inside the region is a paragraph that
#: may never legitimately prescribe anything else. Widened once to cover the
#: whole approval rule, it turned a lawful addition — quoting
#: `method=get → head.sha` next to the HEAD it fetches — into a red reading
#: «the two channels look swapped», which is a false diagnosis pointing an
#: editor at the wrong repair. What the rule *says* is guarded by
#: :data:`APPROVAL_SIGN_REGIONS`, which asks about phrases rather than calls
#: and can therefore span as much prose as it likes.

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
    "the line the review body carries": (
        phrase("Reviewed commit"),
        "the line still exists, but only inside a review body — naming it "
        "is what keeps the next reader from hunting for it in the approval "
        "channel, where Codex stopped writing it and where its absence "
        "means nothing at all",
    ),
    "how long the findings channel's sha is": (
        phrase("префикс в 10 символов"),
        "the review body carries a 10-character prefix, and a reader who "
        "assumes a full sha compares two things that can never be equal",
    ),
    "how long the summary table's sha is": (
        phrase("префикс в 7 символов"),
        "the two channels disagree on length — the review body writes ten "
        "characters, the summary table seven. A reader who carries the "
        "findings channel's ten over to the table slices a sha that is only "
        "seven long and never matches",
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
        phrase("ревью **или строки `Code Review` в сводке Codex**"),
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

#: The approval channel's *contents*, pinned paragraph by paragraph.
#:
#: :data:`CHANNELS` settles which call the approval paragraph makes;
#: this settles what the agent is told to look for in the answer, and that
#: half went stale on its own. Codex changed its scheme: it now keeps one
#: «Codex Review Summary» comment and edits it in place, and when a review
#: finds nothing it writes no new message at all. The old sign — a fresh
#: comment carrying «Reviewed commit» — simply stopped arriving, so §5 read
#: every clean commit as un-reviewed and the PR slept in «На ревью». That is
#: the same failure PR #21 fixed, returning from the other side, which is why
#: the pins here are on the *facts the loop acts on* rather than on prose.
#:
#: Three regions, each bounded by the paragraph that follows it, so that
#: deleting any one of them fails here rather than quietly narrowing the rule:
#:
#: 1. Which row of the table is the sign. The table lists several reviews, and
#:    «отревьюено» is a claim about one of them.
#: 2. Why the Security Review row is *not* compared with HEAD. It has its own
#:    trigger and is not re-run by a push: on PR #27 it stayed on the opening
#:    commit through four of them while Code Review moved on. A rule saying
#:    «every row on HEAD» never converges — the original bug, re-entered.
#: 3. Why the one machine-readable block in the summary is not the sign. It is
#:    the obvious thing to reach for — JSON, in a document otherwise made of
#:    prose — and it belongs to Security Review: on PR #27 it held `9ee5569`
#:    while Code Review was already four commits ahead.
#:
#: Scoped to a region rather than to §5 as a whole, for the reason
#: :data:`CALL_SITES` is: a fact stated somewhere in §5 is not a fact
#: available to the agent standing on this step.
#:
#: Matched through :func:`phrase`, not as plain substrings. The document is
#: hard-wrapped at 78 columns, so every one of these sentences is split across
#: two lines somewhere — a substring check would fail on prose that says
#: exactly the right thing, which is the kind of red that teaches an editor to
#: weaken the guard.
#:
#: Each required entry is a whole sentence rather than a fragment, and that
#: is the load-bearing detail. Mutation testing found the same hole in every
#: region while the pins were fragments: a rule can be cancelled inside its
#: own paragraph with every pinned phrase still present word for word. «А вот
#: строка `Code Review` … признаком как раз не является» contains the pin and
#: means its opposite, and the guard stayed green while the document
#: prescribed the never-converging rule the next region exists to refuse.
#: :data:`REQUIRED_CLAIMS` already knew this about single phrases — its
#: `начинается с` entry says so — and the answer there was to pin word order.
#: Pinning the sentence whole is the same answer at paragraph scale: an
#: inversion has to break the sentence to write itself.
#:
#: A ban list was tried here beside the required set and is deliberately not
#: kept. It killed nothing the whole-sentence pins did not already kill, and
#: seven rewritings walked around it in one sitting — Russian morphology
#: hands out `строка → строчка` and `все → каждую` for free, and two of the
#: seven needed no banned vocabulary at all («записано до смены схемы и
#: больше не действует», «это правило не применяется, когда…»). What would
#: have to be forbidden is not a wording but *a second, contradicting
#: prescription inside the region*, and an enumeration is the wrong shape for
#: that. Keeping the list would have bought the appearance of a fence around
#: a gap of the same size. The gap is real and filed as
#: https://trello.com/c/HGPIC0Y1 ; until then, a paragraph that states a rule
#: and its negation is a contradiction on the page, which is review's to
#: catch and not a test's.
APPROVAL_SIGN_REGIONS = {
    "which row of the summary is the sign": (
        "**Сказать нечего",
        "**Строка `Security Review`",
        (
            phrase("Codex Review Summary"),
            phrase("правит на месте"),
            phrase("Review | Status | Commit | Review trigger"),
            phrase(
                "Признак того, что итерация отревьюена, один: **строка "
                "`Code Review` со статусом `Completed`, чей коммит совпадает "
                "с началом текущего HEAD.**"
            ),
        ),
    ),
    "why the security row is excluded from the comparison": (
        "**Строка `Security Review`",
        "**HTML-блок",
        (
            phrase("**Строка `Security Review` с HEAD не сверяется.**"),
            phrase("на пуши она не перезапускается"),
            phrase("9ee5569"),
            phrase("Правило «все строки таблицы на HEAD» не сойдётся никогда"),
        ),
    ),
    "why the machine-readable block is not the sign": (
        "**HTML-блок",
        "**SHA в ячейке таблицы",
        (
            phrase("codex-security-review:v1"),
            phrase("принадлежит Security Review"),
            phrase("Полного SHA у строки `Code Review` в сводке нет"),
        ),
    ),
    "what to do when no sign is there": (
        "**SHA в ячейке таблицы",
        "Мержит агент сам",
        (
            phrase("префикс в 7 символов"),
            phrase("через «начинается с», а не на равенство"),
            phrase(
                "ни строки `Code Review` со статусом `Completed` и его "
                "префиксом в ячейке — ревью этой версии ещё не было, "
                "мержить нельзя"
            ),
        ),
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

#: The other tool the cloud agent cannot reach, and the reason this file grew a
#: second half.
#:
#: `gh` is absent from the runner image, and installing it does not help: the
#: session's GitHub credentials serve only a pinned set of PR-review
#: operations, so `gh pr list`, `gh pr checks` and `gh api` all answer 403.
#: That is a property of the platform, not of this repository — nothing an
#: editor writes here can make the CLI work again.
#:
#: §6's audit used to gate the whole night on `gh` being functional, and for
#: thirteen consecutive nights it did exactly what it said: the run stopped at
#: the first check and produced nothing. The gate was not wrong when written —
#: `gh` worked then. It became a rule that spent the night to protect an
#: ability the night no longer needed.
#:
#: Banned as a command form rather than as a bare word, and that split is
#: deliberate: the document still has to be able to *name* `gh` in order to
#: explain why it must not come back. A ban on the token alone would forbid
#: the explanation and leave the next editor with a document full of MCP calls
#: and no reason for them — which is precisely the state that invites someone
#: to "finish the migration" in the wrong direction.
#: Matched as a *command form* — `gh` followed by any ASCII word — rather
#: than as a list of subcommands. The first version enumerated eight, and an
#: enumeration is the wrong shape for this: `gh status` and `gh release` are
#: every bit as unrunnable here and sailed straight through it. The CLI's
#: subcommand set belongs to GitHub and grows without asking this file.
#:
#: An ASCII word is what separates a call from an explanation. The document
#: has to keep naming `gh` in prose to say why it must not return, and in
#: Russian prose the next word is Cyrillic or punctuation — never `[a-z]`.
BANNED_TOOL_CALLS = {
    r"`?\bgh\s+[a-z][a-z-]*": (
        "a `gh` command prescribed to the agent. The binary is not in the "
        "image and its API answers 403 — an instruction to run it is an "
        "instruction to fail, and §6 used to turn that failure into a "
        "stopped night"
    ),
}

#: The replacements, each pinned to the *step* that has to prescribe it.
#:
#: Scoped to a region rather than to §5 as a whole, and that is not fussiness:
#: the first version of this guard asked only whether each name appeared
#: somewhere in §5, and a mutation that deleted the fetch from the merge
#: recipe left it green — the prose two hundred lines below still mentioned
#: the command while explaining why it is plain git. A presence check cannot
#: tell a prescription from a reminiscence, and the step, not the section, is
#: what the agent executes.
#:
#: `git fetch origin pull/` is the odd one out — plain git, not MCP — because
#: fetching a PR head needs no API at all. It is pinned here so that a future
#: editor who sees three MCP calls and one git command does not "tidy" it into
#: a fourth MCP call that does not exist.
#: Each entry is matched against the *prescription*, not against any mention
#: of the same name inside the step. That distinction is the difference
#: between a guard and a decoration, and it cost two rounds to learn: the
#: first version pinned bare `create_pull_request`, which occurs twice inside
#: step 9 — once in the fenced call and once in the sentence explaining why an
#: unpushed branch is refused. Deleting the fence outright left the guard
#: green and the step with no call at all. The trailing `(owner=` is what
#: makes the match reach the fence and nothing else.
CALL_SITES = {
    "opening the PR (step 9)": (
        "9. **Закоммитить, запушить, открыть PR.**",
        "10. **Цикл ревью.**",
        ("create_pull_request(owner=",),
    ),
    "closing the iteration (step 10.2)": (
        "2. Замечаний нет,",
        "3. Замечания понятны",
        (
            "pull_request_read method=get_check_runs",
            "merge_pull_request",
            "git fetch origin pull/",
            "git checkout -B <ветка PR> FETCH_HEAD",
        ),
    ),
}

#: What the document must no longer say, and what it must keep saying. The
#: gate needs both halves, because either alone is trivially defeated.
#:
#: The bans are the operative wordings of the old rule. They are checked
#: against the whole document rather than §6 for the reason the reaction ban
#: is: §6 step 3 delegates the entire review loop into §5, so a halt parked in
#: §5 is reached just as surely as one in the audit. Two spellings are listed
#: because the rule survives rephrasing — «остановиться» carries it without
#: the word «дальше» anywhere in sight.
HALTING_PHRASES = {
    "дальше не идти": "the original gate, verbatim",
    "на этом остановиться": "the same rule with the halt spelled the other way",
}

#: The positive half. A ban alone is satisfied by deleting the paragraph that
#: teaches the lesson — the document would then simply fall silent about it,
#: and the next editor, finding no rule, would have no reason not to write the
#: gate back. Pinning the sentence keeps the reasoning in the file that has to
#: carry it.
SECTION_6_CLAIMS = {
    "that a missing tool is not itself a reason to stop": (
        phrase("само по себе ночь не останавливает"),
        "a ban on the halting phrases is satisfied by deleting the paragraph "
        "that teaches the lesson, leaving a document with no position on the "
        "question — and the next editor, finding none, has no reason not to "
        "write the gate back",
    ),
    "that the work is still committed and pushed when MCP is down": (
        phrase("встать\n     ровно перед `create_pull_request`"),
        "step 9 is commit, push and open-PR, and only the last needs MCP. A "
        "fallback that skips the whole step leaves the night's work in a "
        "container that is gone by morning and takes from §6 step 2 the one "
        "thing it recovers state from — the branch on origin",
    ),
}

#: What §6's audit has to be able to *call*, on the same reasoning as
#: :data:`CALL_SITES` in §5: removing `gh` left holes, and a hole reads as a
#: finished document right up until an agent stands on it.
#:
#: The workflow-run lookup is the one that hurts. §6 builds its whole
#: three-way classification — green / red / no answer — on a run object, and
#: after the migration nothing prescribed a call that returns one:
#: `list_workflow_jobs` needs a run id it had no way to obtain. An audit that
#: cannot fetch the run cannot classify it, so «красный master останавливает
#: всё» is either skipped or stuck reading "no answer" forever — the safety
#: gate of the entire night, quietly disarmed.
#:
#: `head_sha` is here as a spelling, not a call: `headSha` is what the removed
#: CLI printed, and the field the MCP response actually carries is
#: `head_sha`. Comparing against a key that is never present makes every run
#: look like it belongs to some other commit, which reads as "no run on this
#: SHA" and re-dispatches CI on every audit.
AUDIT_CALLS = {
    "actions_list method=list_workflow_runs": (
        "fetching the master CI run that the three-way classification reads"
    ),
    "list_pull_requests": "probing that GitHub is reachable at all",
    "head_sha": "the field that run is matched to master by",
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


@pytest.fixture(scope="module")
def section_6(process_doc: str) -> str:
    """§6 as text, on the same terms as §5: read, never restated."""
    match = SECTION_6.search(process_doc)
    assert match, "docs/process.md has no §6 between the §6 and §7 headings"
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
    §5 is 325 lines, and a floor of 50 would let it lose three quarters of
    itself — including every paragraph this guard exists to protect — while
    staying green.

    It is a floor and nothing finer. Mutation testing deleted a four-line
    paragraph and this stayed green, correctly: no line count can catch that,
    and the answer was to pin the paragraph in
    :data:`APPROVAL_SIGN_REGIONS` rather than to tighten the number until it
    fails on any honest edit.
    """
    assert "Цикл ревью" in section_5, "§5 no longer contains the review loop"
    assert len(section_5.splitlines()) > 300, "§5 lost a substantial part"


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


@pytest.mark.parametrize(("region", "spec"), sorted(APPROVAL_SIGN_REGIONS.items()))
def test_the_approval_channel_names_the_sign_that_actually_arrives(
    section_5: str,
    region: str,
    spec: tuple[str, str, tuple[re.Pattern[str], ...]],
) -> None:
    """The approval half of step 10 describes today's Codex, not last month's.

    The call is right — approval does arrive through `get_comments` — and that
    is exactly why this needed its own guard: :data:`CHANNELS` stayed green
    while the thing the agent was told to find inside the answer stopped
    existing. A correct call and a sign that never appears fail the same way
    as a wrong call, and more quietly.
    """
    opening, closing, expected = spec
    start = section_5.find(opening)
    assert start != -1, f"§5 no longer opens {region} with {opening!r}"
    end = section_5.find(closing, start + 1)
    assert end != -1, (
        f"{region} no longer ends at {closing!r} — the paragraph that "
        "follows it is gone, and with it the rule it carried"
    )

    paragraph = section_5[start:end]
    missing = [fact.pattern for fact in expected if not fact.search(paragraph)]
    assert not missing, (
        f"{region}: §5 no longer states {missing}. Each of these is read by "
        "the agent deciding whether the current HEAD has been reviewed; "
        "without one of them the loop either waits for a sign that never "
        "comes or merges on one that belongs to another commit."
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


@pytest.mark.parametrize(("pattern", "why"), sorted(BANNED_TOOL_CALLS.items()))
def test_the_document_prescribes_no_tool_the_agent_cannot_run(
    process_doc: str, pattern: str, why: str
) -> None:
    """No step tells the agent to run a command that cannot succeed.

    Whole-document rather than §5-only, and for the same reason the reaction
    ban is: §6 reads first and sends the agent into §5's loop, so a `gh` call
    parked in the audit would be obeyed just as readily as one in §5.
    """
    found = re.findall(pattern, process_doc)
    assert not found, (
        f"docs/process.md still prescribes {len(found)} `gh` call(s): {why}."
    )


@pytest.mark.parametrize(("site", "spec"), sorted(CALL_SITES.items()))
def test_each_step_prescribes_the_calls_it_needs(
    section_5: str, site: str, spec: tuple[str, str, tuple[str, ...]]
) -> None:
    """Removing `gh` left four holes; each has to be filled, not just emptied.

    A document that deletes the unusable commands without naming replacements
    reads as complete and strands the agent at the first step that needs one —
    the same night-shaped failure as the gate, arriving later.
    """
    opening, closing, expected = spec
    start = section_5.find(opening)
    assert start != -1, f"§5 no longer opens {site} with {opening!r}"
    end = section_5.find(closing, start + 1)
    assert end != -1, f"{site} no longer ends at {closing!r}"

    step = section_5[start:end]
    missing = [call for call in expected if call not in step]
    assert not missing, (
        f"{site} does not prescribe {missing}. Deleting `gh` without naming "
        "what replaces it leaves the step with no call at all — and a mention "
        "elsewhere in §5 does not help the agent standing on this step."
    )


def test_section_6_is_actually_there(section_6: str) -> None:
    """Non-vacuity for §6, on the same terms §5 has it.

    The bans below are `not in`, and that is true of the empty string. Without
    this, renumbering the sections — or any edit that makes the §6/§7 pair stop
    matching — would turn the gate guard into a test that asserts nothing while
    still reporting green.
    """
    assert "**Аудит.**" in section_6, "§6 no longer contains the audit step"
    assert len(section_6.splitlines()) > 90, "§6 lost a substantial part"


@pytest.mark.parametrize(("halt", "why"), sorted(HALTING_PHRASES.items()))
def test_no_section_halts_the_night_over_tooling(
    process_doc: str, halt: str, why: str
) -> None:
    """No section spends the night on a tool it cannot have.

    This is the assertion the whole change exists for. The gate read «не
    работает gh — дальше не идти», and it was obeyed literally on thirteen
    consecutive nights: audit, report, exit, nothing built. The base was green
    throughout — what stopped was the process, over an ability the night had
    already stopped needing.

    Whole-document rather than §6-scoped: §6 step 3 delegates the review loop
    into §5, so a halt written into §5 stops the night just as effectively.
    """
    assert halt not in process_doc, (
        f"docs/process.md still tells the run to stop dead ({halt!r}: {why}). "
        "A missing tool is a fact for the summary, not a reason to spend the "
        "night."
    )


@pytest.mark.parametrize(("call", "job"), sorted(AUDIT_CALLS.items()))
def test_the_audit_prescribes_the_calls_it_runs_on(
    section_6: str, call: str, job: str
) -> None:
    """§6 names a call for every lookup its own rules depend on.

    The gate this change removed was one failure mode; this is the opposite
    one, and it arrives silently. An audit that describes a comparison without
    naming the call that fetches its operand looks complete on the page and
    strands the agent at the first line that needs it — with the difference
    that a missing gate stops the night loudly, and a missing call makes the
    night's most important check quietly unanswerable.
    """
    assert call in section_6, (
        f"§6 no longer names `{call}`, needed for {job}. Its own rules read a "
        "value nothing in the document fetches."
    )


@pytest.mark.parametrize(
    ("claim", "pattern", "why"),
    [(name, pattern, why) for name, (pattern, why) in SECTION_6_CLAIMS.items()],
)
def test_section_6_states_the_rules_that_replaced_the_gate(
    section_6: str, claim: str, pattern: re.Pattern[str], why: str
) -> None:
    """The rules survive, not merely the absence of the old one.

    Both are positive pins, and both exist because a ban alone is satisfied by
    saying nothing at all.
    """
    assert pattern.search(section_6), f"§6 no longer states {claim}: {why}"
