"""The commit gate's own guarantees, pinned by tests.

The gate exists to refuse a commit the machine can already tell is broken.
Every case here is one where it used to say "green" (or "not installed", or
nothing at all) about code that was not the code being committed — that is,
where it handed back exactly the assurance it exists to provide, wrongly.

The guarantee now rests on one fact: the checks run against a materialised
copy of the index, so "the code being committed" and "the code that was
checked" are the same tree by construction rather than by inference.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GATE_PATH = PROJECT_ROOT / "scripts" / "precommit_gate.py"


def _load_gate():
    """Import scripts/precommit_gate.py by path — scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location("precommit_gate", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway git repo the gate's git helpers read instead of this one."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    for key, value in (
        ("user.email", "gate@test"),
        ("user.name", "gate"),
        # Never sign: a developer with commit.gpgsign on globally would
        # otherwise have every test in this file fail on a key prompt.
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "config", key, value], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("v1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
    return tmp_path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _reading(path: str, expected: str) -> gate.Check:
    """A check that passes only when *path*, read from its own working
    directory, holds *expected*.

    This is how a test asks "which tree did the checks actually see?" without
    trusting the gate's own account of it.
    """
    script = (
        "import pathlib, sys;"
        f"p = pathlib.Path({path!r});"
        f"sys.exit(0 if p.is_file() and p.read_text().strip() == {expected!r} else 1)"
    )
    return gate.Check("проба", "проба", [sys.executable, "-c", script], None)


def _decide(monkeypatch, capsys, command: str, checks=None) -> dict:
    """Run main() for *command*, return the hook decision it printed."""
    monkeypatch.setattr(gate, "CHECKS", [] if checks is None else checks)
    payload = json.dumps({"tool_input": {"command": command}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert gate.main() == 0
    return json.loads(capsys.readouterr().out)["hookSpecificOutput"]


def _is_deny(decision: dict) -> bool:
    return decision.get("permissionDecision") == "deny"


def _text(decision: dict) -> str:
    return decision.get("permissionDecisionReason") or decision.get(
        "additionalContext", ""
    )


# ── A check that never started vs. a check that started and found a bug ──────


def test_missing_tool_is_reported_as_missing():
    """``python -m ruff`` without ruff installed: the tool never started."""
    output = "/usr/bin/python3: No module named ruff"
    assert gate._is_module_missing(output, "ruff") is True


def test_import_error_inside_a_running_check_is_not_a_missing_tool():
    """The regression: pytest *did* start and found staged code importing
    a package that does not exist. Reading that as "pytest is not installed"
    skips the check and lets the broken commit through — the gate handing
    back the very guarantee it exists to give, inverted."""
    output = (
        "ImportError while importing test module 'tests/test_x.py'.\n"
        "tests/test_x.py:1: in <module>\n"
        "    import totally_absent_pkg\n"
        "E   ModuleNotFoundError: No module named 'totally_absent_pkg'\n"
    )
    assert gate._is_module_missing(output, "pytest") is False


def test_a_module_whose_name_merely_starts_with_the_tool_is_not_the_tool():
    assert gate._is_module_missing("No module named ruffles", "ruff") is False


def test_the_tools_own_name_quoted_inside_a_check_is_not_a_missing_tool():
    """The same distinction with the names that make it dangerous: the check
    is pytest and the module pytest could not import is *also* called pytest.
    Bare means the interpreter never started the tool; quoted means a tool
    that did start raised ModuleNotFoundError. Match on the substring and
    this output — staged code with a broken import, caught by a check that
    ran — is filed as "pytest is not installed", the check is skipped, and
    the commit passes."""
    output = (
        "ImportError while importing test module 'tests/test_x.py'.\n"
        "tests/test_x.py:1: in <module>\n"
        "    import pytest\n"
        "E   ModuleNotFoundError: No module named 'pytest'\n"
    )
    assert gate._is_module_missing(output, "pytest") is False


def test_a_package_without_an_entry_point_counts_as_a_missing_tool():
    """``python -m ruff`` where ruff imports but has no ``__main__``: the
    tool still never started, so this is an absent check and not a failing
    one."""
    output = (
        "/usr/bin/python3: No module named ruff.__main__; "
        '"ruff" is a package and cannot be directly executed'
    )
    assert gate._is_module_missing(output, "ruff") is True


# ── Which tree the checks actually see ──────────────────────────────────────


def test_a_defect_only_in_the_working_tree_is_caught_too(repo, monkeypatch, capsys):
    """``a.py`` is sound in the index and broken in the tree. The hook fires
    before the whole command line, so ``git add a.py && git commit`` — the
    form this project's process prescribes — commits the broken one, and the
    gate cannot tell that command from a plain ``git commit`` without the
    parse it no longer does. So it checks the tree as well and refuses."""
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("BROKEN\n", encoding="utf-8")

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_reading("a.py", "v1")]
    )

    assert _is_deny(decision)
    assert gate.WORKTREE in _text(decision)


def test_a_defect_only_in_the_index_is_still_caught(repo, monkeypatch, capsys):
    """The same fact the other way round: the working tree is clean and the
    index is broken. A gate that reads the tree calls this green, and the
    broken version is what lands."""
    (repo / "a.py").write_text("BROKEN\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("v1\n", encoding="utf-8")

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_reading("a.py", "v1")]
    )

    assert _is_deny(decision)
    assert gate.INDEX in _text(decision)


def test_untracked_files_are_not_in_the_snapshot(repo, monkeypatch, capsys):
    """Staged code that imports a helper existing only in the working tree.
    The checks pass against the tree and a clean checkout of the commit fails
    on the missing file, so the snapshot must not contain it."""
    (repo / "helper.py").write_text("v1\n", encoding="utf-8")

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_reading("helper.py", "v1")]
    )

    assert _is_deny(decision)


def test_a_half_staged_file_is_checked_rather_than_refused(
    repo, monkeypatch, capsys
):
    """A file staged and then edited further used to stop the gate dead: it
    could not tell which half the commit would carry, so it refused outright.
    The split alone is no longer a reason to refuse — that each half is
    actually read is pinned by the two tests above, on their own scenario."""
    (repo / "a.py").write_text("v2\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("v3\n", encoding="utf-8")

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_reading("b.py", "v1")]
    )

    assert not _is_deny(decision)


def test_the_gate_leaves_the_repository_exactly_as_it_found_it(
    repo, monkeypatch, capsys
):
    """``git stash`` would have done the same job and would have moved the
    developer's work to do it. Taking a copy must not disturb anything."""
    (repo / "a.py").write_text("v2\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("v3\n", encoding="utf-8")
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    _decide(monkeypatch, capsys, "git commit -m x", checks=[_reading("b.py", "v1")])

    after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert after == before
    assert (repo / "a.py").read_text(encoding="utf-8") == "v3\n"


def test_the_snapshot_is_thrown_away_after_the_checks(repo, monkeypatch, capsys):
    """The copy is temporary. A gate that leaves one behind per commit fills
    the disk quietly."""
    seen: list[Path] = []
    original = gate._snapshot_index

    def _remember(destination: Path) -> bool:
        seen.append(destination)
        return original(destination)

    monkeypatch.setattr(gate, "_snapshot_index", _remember)

    _decide(monkeypatch, capsys, "git commit -m x")

    assert seen and not seen[0].exists()


def _counting(tally: Path) -> gate.Check:
    """A check that always passes and records that it ran."""
    script = (
        "import pathlib;"
        f"p = pathlib.Path({str(tally)!r});"
        "p.write_text((p.read_text() if p.exists() else '') + 'x')"
    )
    return gate.Check("счётчик", "счётчик", [sys.executable, "-c", script], None)


def test_a_tree_that_matches_the_index_is_checked_once(
    repo, tmp_path, monkeypatch, capsys
):
    """Nothing outside the index means both trees hold the same content for
    every file the commit could draw from. Running the suite twice over it
    would double the wait a developer feels on every commit and prove
    nothing."""
    tally = tmp_path / "runs"

    _decide(monkeypatch, capsys, "git commit -m x", checks=[_counting(tally)])

    assert tally.read_text() == "x"


def test_a_tree_that_differs_from_the_index_is_checked_as_well(
    repo, tmp_path, monkeypatch, capsys
):
    tally = tmp_path / "runs"
    (repo / "a.py").write_text("v2\n", encoding="utf-8")

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_counting(tally)]
    )

    assert tally.read_text() == "xx"
    assert gate.INDEX in _text(decision)
    assert gate.WORKTREE in _text(decision)


# ── What the pass does not cover, said out loud ─────────────────────────────


def test_the_note_names_the_content_the_snapshot_left_out(
    repo, monkeypatch, capsys
):
    """An unstaged edit and an untracked file are both outside the commit and
    outside the check. ``git commit -a`` would sweep the first one in after
    the gate has run, so the gate says which files that would be."""
    (repo / "a.py").write_text("v2\n", encoding="utf-8")
    (repo / "new.py").write_text("v1\n", encoding="utf-8")

    decision = _decide(monkeypatch, capsys, "git commit -m x")

    note = _text(decision)
    assert not _is_deny(decision)
    assert "a.py" in note
    assert "new.py" in note
    assert "-a" in note


def test_a_clean_tree_gets_no_warning_about_it(repo, monkeypatch, capsys):
    decision = _decide(monkeypatch, capsys, "git commit -m x")

    assert "В рабочем дереве есть" not in _text(decision)


def test_the_listing_stops_before_it_becomes_wallpaper():
    """A clone with build output in it has hundreds of untracked files. A
    note that long is skipped whole, and the one line that mattered goes with
    it."""
    listing = gate._listing([f"f{n}.py" for n in range(gate.MAX_LISTED + 5)])

    assert listing.count("\n") == gate.MAX_LISTED
    assert "f0.py" in listing
    assert f"f{gate.MAX_LISTED}.py" not in listing
    assert "и ещё 5" in listing


def test_a_short_listing_is_not_cut():
    assert gate._listing(["a.py"]) == "  - a.py"


def test_a_staged_file_alone_is_not_reported_as_outside_the_index(
    repo, monkeypatch, capsys
):
    """A fully staged file *is* the commit. Listing it as unchecked content
    would train the developer to ignore the list."""
    (repo / "a.py").write_text("v2\n", encoding="utf-8")
    _git(repo, "add", "a.py")

    assert "a.py" not in gate._outside_the_index()


def test_a_skip_worktree_entry_is_still_in_the_snapshot(repo, monkeypatch, capsys):
    """A sparse checkout marks the paths it does not materialise with
    skip-worktree, and ``git checkout-index -a`` honours that mark on its
    own. Those entries are still in the index, so they are still in the
    commit: a snapshot without them is a subset of what gets recorded, and
    the checks pass over the part that is missing."""
    _git(repo, "update-index", "--skip-worktree", "b.py")

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_reading("b.py", "v1")]
    )

    assert not _is_deny(decision)


# ── When the snapshot cannot be taken ───────────────────────────────────────


def test_a_failed_snapshot_is_reported_and_not_passed_off_as_a_check(
    repo, monkeypatch, capsys
):
    """No git, no repository, a broken index. Checking the working tree is
    worth more than checking nothing, but it is a different tree — and a
    weaker guarantee handed back as the full one is the failure this gate
    exists to prevent."""
    monkeypatch.setattr(gate, "_snapshot_index", lambda destination: False)
    (repo / "a.py").write_text("worktree only\n", encoding="utf-8")

    decision = _decide(
        monkeypatch,
        capsys,
        "git commit -m x",
        checks=[_reading("a.py", "worktree only")],
    )

    assert not _is_deny(decision)
    assert "Снимок индекса собрать не удалось" in _text(decision)


def test_a_snapshot_that_cannot_be_written_degrades_instead_of_killing_the_hook(
    repo, monkeypatch, capsys
):
    """A read-only filesystem, a full disk, a directory the user cannot
    write: the snapshot fails before git is ever reached. An exception there
    escapes the hook, which then prints no decision at all — and standing
    aside silently is the one failure the gate cannot recover from."""
    real_mkdir = Path.mkdir

    def refuse(self, *args, **kwargs):
        if "precommit-gate-" in str(self):
            raise PermissionError(13, "Read-only file system")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse)

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_reading("a.py", "v1")]
    )

    assert not _is_deny(decision)
    assert "Снимок индекса собрать не удалось" in _text(decision)


def test_a_gate_that_falls_over_refuses_instead_of_standing_aside(
    repo, monkeypatch, capsys
):
    """A PreToolUse hook that prints nothing blocks nothing: the commit sails
    through exactly as if the gate had approved it. So whatever breaks —
    here, git itself — the answer has to be a refusal, and exactly one."""

    def explode(*args, **kwargs):
        raise RuntimeError("git ушёл под воду")

    monkeypatch.setattr(gate, "_outside_the_index", explode)
    monkeypatch.setattr(gate, "CHECKS", [])
    payload = json.dumps({"tool_input": {"command": "git commit -m x"}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    assert gate.main() == 0

    printed = capsys.readouterr().out
    decision = json.loads(printed)["hookSpecificOutput"]
    assert _is_deny(decision)
    assert "гейт упал" in _text(decision)


def test_a_snapshot_left_behind_is_removed_even_when_the_checks_blow_up(
    repo, monkeypatch, capsys
):
    """The copy is temporary. One left behind per failed commit fills the
    disk quietly, and failures are exactly when nobody is looking."""
    seen: list[Path] = []
    original = gate._snapshot_index

    def remember(destination: Path) -> bool:
        seen.append(destination)
        return original(destination)

    monkeypatch.setattr(gate, "_snapshot_index", remember)
    monkeypatch.setattr(gate, "_judge", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": "git commit"}})))

    assert gate.main() == 0

    assert seen and not seen[0].exists()


def test_git_that_cannot_answer_buys_the_tree_a_run_rather_than_costing_it_one(
    repo, tmp_path, monkeypatch, capsys
):
    """``_outside_the_index`` returning None means git timed out or refused,
    not that the tree is clean. Read as clean it would cancel the working-tree
    run without a word — and the bigger the repository, the likelier git is
    to be the one that gives up."""
    monkeypatch.setattr(gate, "_outside_the_index", lambda: None)
    tally = tmp_path / "runs"

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_counting(tally)]
    )

    assert tally.read_text() == "xx"
    assert gate.WORKTREE in _text(decision)
    assert "git не ответил" in _text(decision)


def test_a_check_that_times_out_is_a_refusal_not_a_skipped_check(
    repo, monkeypatch, capsys
):
    """A check that never finished proved nothing. Filing it beside "the tool
    is not installed" would turn the slowest possible failure into a pass."""

    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="проба", timeout=180)

    monkeypatch.setattr(subprocess, "run", hang)

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_reading("a.py", "v1")]
    )

    assert _is_deny(decision)
    assert "не уложился" in _text(decision)


@pytest.mark.parametrize("payload", ["[]", "null", "5", '{"tool_input": 5}', '{"tool_input": null}'])
def test_a_payload_of_the_wrong_shape_does_not_kill_the_hook(monkeypatch, capsys, payload):
    """``[]`` and ``null`` are valid JSON, so the json.load guard does not
    catch them; reaching for .get on them raises AttributeError, the hook
    dies without printing, and a hook that prints nothing blocks nothing."""
    monkeypatch.setattr(gate, "CHECKS", [])
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    assert gate.main() == 0
    assert capsys.readouterr().out == ""


def test_a_failed_snapshot_still_denies_a_failing_check(repo, monkeypatch, capsys):
    monkeypatch.setattr(gate, "_snapshot_index", lambda destination: False)

    decision = _decide(
        monkeypatch,
        capsys,
        "git commit -m x",
        checks=[_reading("a.py", "something else")],
    )

    assert _is_deny(decision)
    assert "Снимок индекса собрать не удалось" in _text(decision)


def test_an_empty_snapshot_is_an_absent_check_not_a_failing_one(
    repo, monkeypatch, capsys
):
    """pytest exits 5 when it collected nothing, which is what a snapshot of
    an empty index gives it. Denying over that is a refusal the developer
    cannot act on."""
    empty = gate.Check(
        "проба", "проба", [sys.executable, "-c", "raise SystemExit(5)"], 5
    )

    decision = _decide(monkeypatch, capsys, "git commit -m x", checks=[empty])

    assert not _is_deny(decision)
    assert "проверять нечего" in _text(decision)


def test_an_empty_index_still_gets_its_checks_run(repo, monkeypatch, capsys):
    """``git checkout-index`` writes only the directories it has files to put
    in, so an empty index leaves none at all. A check pointed at a path that
    does not exist comes back as FileNotFoundError, which this gate forgives
    as "the tool is not installed" — an unchecked commit arriving dressed as
    a green one."""
    _git(repo, "rm", "-r", "-q", "--cached", ".")

    decision = _decide(
        monkeypatch, capsys, "git commit -m x", checks=[_reading("a.py", "v1")]
    )

    assert _is_deny(decision)
    assert "интерпретатор не найден" not in _text(decision)


def test_the_same_exit_status_from_a_check_that_has_no_empty_code_is_a_failure(
    repo, monkeypatch, capsys
):
    failing = gate.Check(
        "проба", "проба", [sys.executable, "-c", "raise SystemExit(5)"], None
    )

    decision = _decide(monkeypatch, capsys, "git commit -m x", checks=[failing])

    assert _is_deny(decision)


# ── When the gate stands aside ──────────────────────────────────────────────


def test_a_command_without_a_commit_is_left_alone(repo, monkeypatch, capsys):
    """A hook registered for every Bash call must not answer ``git status``
    with a full test run — and must not deny the commands someone runs to
    diagnose a failing test."""
    monkeypatch.setattr(gate, "CHECKS", [])
    payload = json.dumps({"tool_input": {"command": "git status"}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    assert gate.main() == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "command",
    [
        "GIT_AUTHOR_DATE=x git commit -m x",
        "env FOO=1 git commit -m x",
        'git commit -m"fix thing"',
        "git -C . commit -m x",
        "git add a.py missing || git commit -m x",
        "make commit",
    ],
)
def test_anything_that_says_commit_is_checked(repo, monkeypatch, capsys, command):
    """Standing aside is the one outcome the gate cannot recover from: it
    does not refuse, does not warn and leaves no trace. So the test for it is
    deliberately cruder than any parse — an assignment, a wrapper, an
    unspaced ``-m``, a shell operator that inverts which command runs. All of
    these once talked the gate out of checking; a false positive here costs a
    test run, and only that."""
    decision = _decide(monkeypatch, capsys, command)

    # Standing aside prints nothing at all, which _decide cannot parse. Get
    # this far and the gate ran; the note is what it says when it did.
    assert "Проверки прошли" in _text(decision)


def test_a_broken_payload_does_not_kill_the_hook(monkeypatch, capsys):
    monkeypatch.setattr(gate, "CHECKS", [])
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json at all"))

    assert gate.main() == 0
    assert capsys.readouterr().out == ""
