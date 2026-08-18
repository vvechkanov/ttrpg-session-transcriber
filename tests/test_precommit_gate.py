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
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "gate@test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "gate"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("v1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    monkeypatch.setattr(gate, "PROJECT_ROOT", tmp_path)
    return tmp_path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True)


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
    ],
)
def test_path_selecting_commits_do_not_describe_the_index(command):
    """``git commit -- a.py`` records that path and leaves the rest of the
    index alone, so no index-derived conclusion maps onto the commit."""
    assert gate._commit_selects_paths(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "git commit",
        'git commit -m "a.py fixes"',
        'git commit -am "msg"',
        "git commit --no-verify",
    ],
)
def test_ordinary_commits_do_describe_the_index(command):
    assert gate._commit_selects_paths(command) is False


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
