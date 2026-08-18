"""The commit gate's own guarantees, pinned by tests.

The gate exists to refuse a commit the machine can already tell is broken.
Every case here is one where it used to say "green" (or "not installed", or
nothing at all) about code that was not the code being committed — that is,
where it handed back exactly the assurance it exists to provide, wrongly.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
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


def _shape(command: str):
    """The shape of the single ``git commit`` in *command*."""
    plan = gate._plan(command)
    assert plan.commits, f"command should contain a commit: {command!r}"
    return gate._commit_shape(plan.commits[0])


def _selects_paths(command: str) -> bool:
    """Whether any ``git commit`` in *command* names the paths it records."""
    plan = gate._plan(command)
    assert plan.commits, f"command should contain a commit: {command!r}"
    return any(gate._commit_shape(argv).selects_paths for argv in plan.commits)


def _restaged(command: str) -> set[str] | None:
    plan = gate._plan(command)
    return gate._restaged_paths(plan, [gate._commit_shape(a) for a in plan.commits])


def _decide(monkeypatch, capsys, command: str) -> dict:
    """Run main() for *command* with the checks stubbed out, return its JSON."""
    monkeypatch.setattr(gate, "CHECKS", [])
    payload = json.dumps({"tool_input": {"command": command}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert gate.main() == 0
    return json.loads(capsys.readouterr().out)["hookSpecificOutput"]


def _is_deny(decision: dict) -> bool:
    return decision.get("permissionDecision") == "deny"


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


# ── What the commit will actually contain ───────────────────────────────────


def test_untracked_files_count_as_working_tree_the_commit_will_not_carry(repo):
    """Staged code can import a helper that exists only as an untracked file:
    the checks pass, and a clean checkout of the commit fails."""
    (repo / "helper_new.py").write_text("HELPER = 1\n", encoding="utf-8")
    (repo / "a.py").write_text("v2\n", encoding="utf-8")
    _git(repo, "add", "a.py")

    assert "helper_new.py" in gate._dirty_elsewhere()


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "msg" -- a.py',
        "git commit --only a.py",
        "git commit -o a.py",
        "git commit a.py",
        # No pathspec spelled out, but --only/-o still means "the paths, not
        # the index" — and these reach the flag branches that a bare pathspec
        # would otherwise mask.
        "git commit --only",
        "git commit -o",
    ],
)
def test_path_selecting_commits_do_not_describe_the_index(command):
    """``git commit -- a.py`` records that path and leaves the rest of the
    index alone, so no index-derived conclusion maps onto the commit."""
    assert _selects_paths(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "git commit",
        'git commit -m "a.py fixes"',
        'git commit -am "msg"',
        "git commit --no-verify",
        'git commit -m "fix -- broken"',
        'git commit --author "A <a@b.c>" -m msg',
    ],
)
def test_ordinary_commits_do_describe_the_index(command):
    assert _selects_paths(command) is False


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "x" && git push',
        'git commit -m "x"; git log --oneline -1',
        'git commit -m "x"\ngit push',
        'git commit -m "x" 2>&1',
        'git commit -m "x" >/dev/null',
        'git commit -m "a && b"',
    ],
)
def test_what_follows_the_commit_is_not_a_pathspec(command):
    """The regression a naive tokeniser reintroduces: `shlex` knows nothing
    about `;`, newlines or redirections, so everything after the commit
    looked like a pathspec — and the gate switched itself off silently on the
    multi-line command blocks that are the common case."""
    assert _selects_paths(command) is False


def test_path_selecting_commit_is_not_denied_over_an_unrelated_file(
    repo, monkeypatch, capsys
):
    """a.py is staged and dirty, but the commit only records b.py, so a.py's
    split state says nothing about it — denying here is a false alarm."""
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    assert not _is_deny(_decide(monkeypatch, capsys, "git commit -m x -- b.py"))


# ── Commands that stage their own files ─────────────────────────────────────


def test_partial_stage_survives_a_compound_command(repo, monkeypatch, capsys):
    """The regression: ``git add b.py && git commit`` used to switch the
    conflict check off wholesale. ``git add b.py`` does not restage a.py, so
    a.py stays half-staged — the checks see its working-tree version and the
    commit records the older index one."""
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")
    (repo / "b.py").write_text("v2\n", encoding="utf-8")

    decision = _decide(monkeypatch, capsys, 'git add b.py && git commit -m "x"')

    assert _is_deny(decision)
    assert "a.py" in decision["permissionDecisionReason"]


def test_file_the_command_restages_is_not_reported_as_conflicted(
    repo, monkeypatch, capsys
):
    """The false alarm that switching the check off was meant to cure:
    ``git add a.py`` is about to make a.py whole, so it is not a conflict."""
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    assert not _is_deny(_decide(monkeypatch, capsys, 'git add a.py && git commit -m "x"'))


def test_a_directory_pathspec_covers_the_files_under_it(repo, monkeypatch, capsys):
    (repo / "pkg").mkdir()
    (repo / "pkg" / "m.py").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "pkg/m.py")
    _git(repo, "commit", "-qm", "add pkg")
    (repo / "pkg" / "m.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "pkg/m.py")
    (repo / "pkg" / "m.py").write_text("worktree\n", encoding="utf-8")

    assert not _is_deny(_decide(monkeypatch, capsys, 'git add pkg && git commit -m "x"'))


@pytest.mark.parametrize("command", ["git add . && git commit", "git add -A && git commit"])
def test_staging_everything_leaves_nothing_to_conflict(repo, monkeypatch, capsys, command):
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    assert not _is_deny(_decide(monkeypatch, capsys, command))


def test_plain_commit_still_denies_a_half_staged_file(repo, monkeypatch, capsys):
    """The gate's original purpose, still intact."""
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    decision = _decide(monkeypatch, capsys, 'git commit -m "x"')

    assert _is_deny(decision)
    assert "a.py" in decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "x"; git log',
        'git commit -m "x"\ngit push',
        'git commit -m "x" 2>&1',
    ],
)
def test_a_half_staged_file_is_still_caught_past_a_shell_operator(
    repo, monkeypatch, capsys, command
):
    """A command block must not be able to silence the gate."""
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    assert _is_deny(_decide(monkeypatch, capsys, command))


def test_every_git_add_in_the_line_counts_not_just_the_first(repo, monkeypatch, capsys):
    (repo / "pkg").mkdir()
    (repo / "pkg" / "m.py").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "pkg/m.py")
    _git(repo, "commit", "-qm", "add pkg")
    for path in ("a.py", "pkg/m.py"):
        (repo / path).write_text("staged\n", encoding="utf-8")
        _git(repo, "add", path)
        (repo / path).write_text("worktree\n", encoding="utf-8")

    command = 'git add a.py && git add pkg/m.py && git commit -m "x"'
    assert not _is_deny(_decide(monkeypatch, capsys, command))


@pytest.mark.parametrize("spelling", ["./a.py", r"a.py"])
def test_pathspecs_are_matched_in_the_shape_git_reports_them(
    repo, monkeypatch, capsys, spelling
):
    """``./a.py`` and a backslash-separated Windows path both name the file
    git calls ``a.py``; missing that denies a perfectly good commit."""
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    command = f'git add {spelling} && git commit -m "x"'
    assert not _is_deny(_decide(monkeypatch, capsys, command))


def test_windows_style_pathspec_normalises_to_forward_slashes():
    assert _restaged(r"git add scripts\gate.py && git commit") == {"scripts/gate.py"}


def test_commit_dash_a_stages_everything_so_nothing_stays_conflicted(
    repo, monkeypatch, capsys
):
    """``git commit -a`` restages every tracked change, so a half-staged
    tracked file is about to become whole."""
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    assert not _is_deny(_decide(monkeypatch, capsys, 'git commit -am "x"'))


@pytest.mark.parametrize("flag", ["-A", "-u", "--all", "--update"])
def test_a_widening_flag_still_obeys_the_pathspec_beside_it(flag):
    """``-A`` and ``-u`` widen *what kinds of change* are staged, not *where*
    (``git add [<options>] [--] <pathspec>...``). Reading them as "the whole
    tree" would clear the conflict on every other half-staged file."""
    assert _restaged(f"git add {flag} b.py && git commit") == {"b.py"}


@pytest.mark.parametrize("flag", ["-A", "-u", "--all", "--update"])
def test_a_widening_flag_without_a_pathspec_does_mean_everything(flag):
    assert _restaged(f"git add {flag} && git commit") is None


@pytest.mark.parametrize("command", ["git commit -mdata", "git commit -mhello"])
def test_an_attached_message_is_not_read_as_a_cluster_of_flags(command):
    """`-mdata` is the message `data`. Scanning it letter by letter finds an
    `a` and calls the commit `-a`, or an `o` and calls it `--only` — either
    way the gate drops the checks on a commit that stages nothing of the
    kind."""
    shape = _shape(command)
    assert shape.stages_everything is False
    assert shape.selects_paths is False


def test_an_unquoted_comment_is_not_a_pathspec():
    """`git commit -m x  # note` — the tail is a shell comment, and reading
    it as a pathspec switches the gate off."""
    assert _selects_paths("git commit -m x # ordinary note") is False


def test_interactive_add_settles_nothing_in_advance():
    """`git add -p` stages the hunks a human picks, so the index it leaves
    cannot be read off the command line."""
    assert _restaged("git add -p a.py && git commit -m x") == set()


def test_an_add_after_the_commit_does_not_count():
    """`git commit -m x; git add a.py` commits the old index first."""
    assert _restaged("git commit -m x; git add a.py") == set()


def test_a_command_that_rewrites_files_before_committing_credits_nothing():
    """The checks run before the whole line. If something writes a.py after
    they finish, they measured code that no longer exists — crediting the
    later `git add` would hide exactly that."""
    command = "printf 'broken(\\n' > a.py && git add a.py && git commit -m x"
    assert _restaged(command) == set()


@pytest.mark.parametrize(
    "prefix", ["cd /repo && ", "git status && ", "git diff --stat && "]
)
def test_harmless_commands_before_the_add_do_not_cost_the_credit(prefix):
    assert _restaged(f"{prefix}git add a.py && git commit -m x") == {"a.py"}


@pytest.mark.parametrize(
    "command",
    [
        "git -C . commit -m x",
        "git -c user.name=x commit -m y",
        "git --git-dir=.git commit -m z",
    ],
)
def test_git_global_options_do_not_hide_the_subcommand(command):
    """``git [-C <path>] … <command>``. Reading ``-C`` as the subcommand made
    the gate stand aside from a commit entirely — the worst outcome available,
    since it skips every check without saying so."""
    assert gate._plan(command).commits, f"should be seen as a commit: {command!r}"


@pytest.mark.parametrize("flag", ["-i", "--include"])
def test_include_commits_the_index_too_so_it_still_needs_checking(flag):
    """``--include`` adds the named paths *to* the index and commits the lot;
    ``--only`` commits the paths *instead of* it. Treating them alike drops
    the checks on every other half-staged file."""
    shape = _shape(f"git commit {flag} a.py -m x")

    assert shape.selects_paths is False
    assert _restaged(f"git commit {flag} a.py -m x") == {"a.py"}


@pytest.mark.parametrize("command", ["git commit -p -m x", "git commit --interactive"])
def test_interactive_commit_settles_nothing_in_advance(command):
    """A human picks hunks after the gate has run, so a whole-file fix in the
    working tree can pass the checks while the chosen snapshot stays broken."""
    assert _shape(command).uncreditable is True
    assert _restaged(command) == set()


def test_interactive_commit_overrides_an_earlier_add(repo, monkeypatch, capsys):
    """``git add a.py && git commit -p`` — the add makes a.py whole, but the
    commit then records only the hunks a human picks, so the add settles
    nothing after all."""
    assert _restaged("git add a.py && git commit -p -m x") == set()

    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    assert _is_deny(_decide(monkeypatch, capsys, "git add a.py && git commit -p -m x"))


def test_a_later_no_all_cancels_the_earlier_dash_a():
    """``-a, --[no-]all`` — git applies the last one."""
    assert _shape("git commit -a --no-all -m x").stages_everything is False
    assert _shape("git commit --no-all -a -m x").stages_everything is True


def test_add_refresh_stages_nothing():
    """``--refresh`` is documented as "don't add, only refresh the index", so
    the staged content stays exactly as it was."""
    assert _restaged("git add --refresh a.py && git commit -m x") == set()


def test_a_command_without_a_commit_is_left_alone(repo, monkeypatch, capsys):
    """The hook may be registered for every Bash call. Running the suite on
    `git status` would deny the very commands someone runs to diagnose a
    failing test."""
    monkeypatch.setattr(gate, "CHECKS", [])
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": "git status"}}))
    )

    assert gate.main() == 0
    assert capsys.readouterr().out == ""


def test_an_unreadable_command_is_not_read_as_staging_everything(
    repo, monkeypatch, capsys
):
    """An unbalanced quote means the gate does not know what will be staged.
    It must then report the index as it stands — a needless refusal is
    visible and recoverable, a silent pass is the failure it exists to
    prevent."""
    (repo / "a.py").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    (repo / "a.py").write_text("worktree\n", encoding="utf-8")

    assert _is_deny(_decide(monkeypatch, capsys, 'git add a.py && git commit -m "unmatched'))
