"""The tier-2 end-to-end run is a manual step, and that has to stay true.

`tests/test_e2e_tier2_semantic.py` runs the whole pipeline and compares the
result to a frozen baseline. It carries `slow` and `requires_asr`, and CI
deselects both — so it has never run in CI and, by decision, never will: the
faster-whisper bundle it needs is ~3.2 GB (ADR-022).

`CONTRIBUTING.md` therefore hands the run to a person and says when it is owed.
That promise rests on facts about this repository that can rot without anyone
noticing: the markers can come off the tier-2 tests, or CI can grow a step that
collects them. Either turns the document into a lie while every other check
stays green.

**These checks ask pytest rather than imitate it.** An earlier version of this
file modelled collection itself — parsing `-m` expressions, matching target
paths, expanding globs. Every round of review found another rule it had got
wrong (chained commands, `pytestmark` scope, shell globs, `--ignore`), which is
the expected outcome: a second implementation of somebody else's selection
logic is wrong in exactly the cases nobody thought of. So each pytest command
in every workflow is now handed back to pytest with `--collect-only`, and the
question "would CI run this suite" is answered by the program that decides it.
Collection of the whole tree costs under a second.

What they cannot check is whether anybody actually ran it. That half is a
promise, and it is meant to read as one.
"""

from __future__ import annotations

import ast
import glob as globlib
import re
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TIER2 = PROJECT_ROOT / "tests" / "test_e2e_tier2_semantic.py"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"
WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"

#: A marker expression that selects everything, used to ask "what would this
#: command collect if it filtered nothing". Appended rather than stripped: the
#: last `-m` wins, so this is immune to `-m EXPR`, `-m=EXPR` and `-mEXPR` alike.
SELECTS_EVERYTHING = "slow or not slow"

#: Console-verbosity options. Dropped from a probed command so the collection
#: listing keeps the one-node-id-per-line shape this file reads. They cannot
#: change *what* pytest collects, only how it prints it.
VERBOSITY = re.compile(r"^(-[qv]+|--quiet|--verbose|--verbosity(=.*)?)$")

#: The markers that keep the tier-2 run out of CI.
KEEPS_IT_OUT = ("slow", "requires_asr")

#: What `CONTRIBUTING.md` has to name as a moment the manual run comes due.
#: `core/` and `domain/` are in the list because `core/pipeline.py` reads
#: `core.discovery`, `core.session_clock`, `core.chunking` and the `domain`
#: types: naming only the obvious paths would tell a contributor editing
#: `core/session_clock.py` that they owe nothing, which is exactly the change
#: most likely to move timestamps in the frozen output.
OWED_ON = ("release", "sources/", "mergers/", "renderers/", "core/", "domain/")

#: Repository scripts a CI step may invoke without this file looking inside.
#: Empty, and each future entry needs a reason: a step that runs a script from
#: this tree could run pytest inside it, and "the word pytest is not in the
#: YAML" is not evidence that it does not.
SCRIPTS_THAT_CANNOT_RUN_TESTS: dict[str, str] = {}

SCRIPT_SUFFIXES = (".sh", ".py", ".ps1", ".bat", ".cmd")


def _commands(script: str) -> list[list[str]]:
    """Split one `run:` block into shell commands, as token lists.

    Separators matter: `pytest … -m "slow" ; pytest … -m "not slow"` is two
    commands, and reading it as one lets the second's harmless selection stand
    in for the first's.
    """
    commands: list[list[str]] = []
    for line in script.replace("\\\n", " ").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:
            raise AssertionError(f"cannot read this CI command line: {line!r}") from None
        # A newline ends a command as surely as a `;` does — losing that turns
        # two steps into one, and the second one's arguments then answer for
        # the first.
        commands.append([])
        for token in tokens:
            if token and all(character in ";&|<>" for character in token):
                commands.append([])
            else:
                commands[-1].append(token)
    return [command for command in commands if command]


def _workflow_files() -> list[Path]:
    """Every workflow in the repository, not just `ci.yml`.

    The promise in `CONTRIBUTING.md` is that *CI* never runs the tier-2 suite,
    and `release.yml` is CI too. Reading one file would leave the other free to
    add the run without anything noticing.
    """
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert files, f"no workflows under {WORKFLOWS.relative_to(PROJECT_ROOT)}"
    return files


def _steps() -> list[tuple[list[list[str]], Path]]:
    """Every `run:` step in every workflow, with the directory it runs in."""
    steps = []
    for path in _workflow_files():
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(workflow, dict) or "jobs" not in workflow:
            continue
        workflow_default = workflow.get("defaults", {}).get("run", {}).get("working-directory")
        for job in workflow["jobs"].values():
            job_default = job.get("defaults", {}).get("run", {}).get("working-directory")
            for step in job.get("steps", []):
                if "run" not in step:
                    continue
                where = step.get("working-directory") or job_default or workflow_default or "."
                steps.append((_commands(step["run"]), PROJECT_ROOT / where))
    return steps


#: Package managers that name `pytest` as a thing to install rather than run.
#: `pip install PySide6 pytest pytest-qt` is not a test run, and reading it as
#: one hands pytest a package name as a path.
INSTALLERS = frozenset({"pip", "pip3", "uv", "conda", "apt-get", "apt", "choco", "brew"})


def _program(token: str) -> str:
    """The bare program name in a token, across platforms.

    `pytest.exe` on the Windows half of the matrix is the same launcher as
    `pytest` on the Linux half, and `C:\\hostedtoolcache\\…\\pytest.exe` is too.
    A reader that knows only the Unix spelling stops guarding one of the two
    operating systems this project supports.
    """
    name = PurePosixPath(token.replace("\\", "/")).name.lower()
    return name[:-4] if name.endswith(".exe") else name


def _is_pytest(token: str) -> bool:
    return _program(token) in ("pytest", "py.test")


def _is_install(command: list[str]) -> bool:
    head = _program(command[0])
    if head in INSTALLERS or (head == "sudo" and len(command) > 1 and command[1] in INSTALLERS):
        return True
    return head.startswith("python") and "-m" in command[:2] and "pip" in command[:3]


def _pytest_arguments(command: list[str]) -> list[str] | None:
    """The arguments of the pytest run in *command*, or None if there is none.

    Deliberately generous about how pytest is launched — bare, `python -m
    pytest`, or behind a launcher like `poetry run`. Missing an invocation
    makes this file quietly stop guarding; misreading one makes it fail loudly,
    and loudly is the better way to be wrong.
    """
    if not command or _is_install(command):
        return None
    for index, token in enumerate(command):
        if _is_pytest(token):
            return command[index + 1 :]
    return None


def _pytest_invocations() -> list[tuple[list[str], Path]]:
    """Each pytest command in the workflow, as (arguments, working directory)."""
    invocations = []
    for commands, where in _steps():
        for command in commands:
            arguments = _pytest_arguments(command)
            if arguments is not None:
                invocations.append((arguments, where))
    return invocations


def _expand(arguments: list[str], where: Path) -> list[str]:
    """Expand shell globs the way the shell would before pytest sees them."""
    expanded = []
    for argument in arguments:
        if any(character in argument for character in "*?["):
            matches = sorted(globlib.glob(argument, root_dir=where))
            expanded.extend(matches or [argument])
        else:
            expanded.append(argument)
    return expanded


def _collects_tier2(arguments: list[str], where: Path) -> bool:
    """Would `pytest <arguments>` in *where* collect the tier-2 module?

    Answered by pytest itself. `-m` expressions, `--ignore`, `--deselect`,
    `testpaths` from pytest.ini when no target is given — all of it is pytest's
    to decide, and none of it is re-implemented here.
    """
    # `-o addopts=` clears the `-v` in pytest.ini, and every verbosity flag from
    # CI's own line goes with it. Not to change what is collected — verbosity
    # cannot — but to pin the listing format. One notch up and the listing
    # carries module docstrings, and this file's docstring names the tier-2
    # module, so matching that text answers yes to everything; one notch down
    # (`-qq`) and pytest prints `path: count` with no node ids at all, so
    # matching answers no to everything.
    pinned = [a for a in _expand(arguments, where) if not VERBOSITY.match(a)]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "--no-header"]
        + ["-p", "no:cacheprovider", "-o", "addopts="]
        + pinned
        + ["-q"],
        cwd=where,
        capture_output=True,
        text=True,
        timeout=300,
    )
    # Only two outcomes are answers: something was collected, or nothing was.
    # An import error, an internal error or a bad option produce empty output
    # that reads exactly like "tier-2 is not collected" — the dangerous way to
    # be wrong, so refuse to interpret it.
    assert result.returncode in (0, 5), (
        f"pytest could not answer for `pytest {' '.join(arguments)}` in "
        f"{where}: exit {result.returncode}. Until that is fixed this check "
        f"cannot tell a safe command from a dangerous one.\n"
        f"{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
    )
    node_ids = [line.split("::")[0] for line in result.stdout.splitlines() if "::" in line]
    return any(Path(node).name == TIER2.name for node in node_ids)


# ── the checks ──────────────────────────────────────────────────────────────


def test_no_step_in_ci_collects_the_tier2_suite():
    invocations = _pytest_invocations()
    assert invocations, (
        "no pytest invocation found in ci.yml. Either CI stopped running tests, "
        "or this check stopped being able to read it — both make it worthless."
    )
    for arguments, where in invocations:
        assert not _collects_tier2(arguments, where), (
            f"CI would collect {TIER2.name}: `pytest {' '.join(arguments)}` in "
            f"{where.relative_to(PROJECT_ROOT)}/. That is a change of decision, "
            f"not of code — either CI grew a 3.2 GB model bundle, or "
            f"CONTRIBUTING.md and ADR-022 are now lying about who runs this suite."
        )


def test_some_step_in_ci_would_have_collected_it_but_for_the_markers():
    """Guards the check above against passing because nothing matched.

    Every clause in it is a `continue` away from vacuous truth. Dropping the
    marker selection from CI's own command has to flip the answer; if it does
    not, CI no longer covers `tests/` at all and the check above proves nothing.
    """
    for arguments, where in _pytest_invocations():
        unfiltered = [*arguments, "-m", SELECTS_EVERYTHING]
        if _collects_tier2(unfiltered, where):
            return
    raise AssertionError(
        "no pytest step in ci.yml reaches tests/test_e2e_tier2_semantic.py even "
        "with the marker selection removed — so the check that CI excludes it "
        "is true for the wrong reason."
    )


def test_the_tier2_tests_still_carry_both_markers():
    """The same fact, said in the language the documents use.

    Redundant with collection on purpose: when this file goes red, the two
    failures together say whether the markers moved or the workflow did.
    """
    tree = ast.parse(TIER2.read_text(encoding="utf-8"))
    tests = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    assert tests, f"{TIER2.name} defines no test functions"

    # Read from the tree, not from the text: the module's own docstring
    # explains both markers by name, so a substring search answers yes long
    # after the last decorator is gone.
    applied = set()
    for node in ast.walk(tree):
        decorators = list(getattr(node, "decorator_list", []))
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        ):
            value = node.value
            decorators += value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        for decorator in decorators:
            call = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(call, ast.Attribute) and isinstance(call.value, ast.Attribute):
                if call.value.attr == "mark":
                    applied.add(call.attr)

    for marker in KEEPS_IT_OUT:
        assert marker in applied, (
            f"{TIER2.name} no longer applies pytest.mark.{marker} anywhere. "
            f"CONTRIBUTING.md says CI never runs the tier-2 suite; without both "
            f"markers CI would try, and fail for want of a 3.2 GB model bundle."
        )


def test_no_ci_step_hides_its_tests_behind_a_repository_script():
    """A wrapper the reader cannot see into is not evidence of anything.

    `run: scripts/ci-tests.sh` contains no pytest command, so every check above
    would skip it while the script inside ran the tier-2 suite. Rather than
    guess, fail and ask for the wrapper to be named here.
    """
    for commands, where in _steps():
        for command in commands:
            if any(_is_pytest(token) for token in command):
                continue
            for token in command:
                if not token.lower().endswith(SCRIPT_SUFFIXES):
                    continue
                # Resolved against the step's own directory: `working-directory:
                # tests` plus `bash ci.sh` means tests/ci.sh, and looking only at
                # the root would walk past it.
                if not (where / token).exists():
                    continue
                assert token in SCRIPTS_THAT_CANNOT_RUN_TESTS, (
                    f"CI runs {token}, a script from this repository, and this "
                    f"file cannot see whether it invokes pytest. Either add the "
                    f"pytest command to the workflow where it can be read, or "
                    f"list {token} in SCRIPTS_THAT_CANNOT_RUN_TESTS with a reason."
                )


# ── the document that carries the half a machine cannot check ───────────────


def _tier2_section() -> str:
    """The body of the CONTRIBUTING section about the tier-2 run.

    Fence-aware: `# One-time bundle install` inside a ```bash block is a shell
    comment, not a heading, and reading it as one cuts the section in half.
    """
    lines = CONTRIBUTING.read_text(encoding="utf-8").splitlines()
    inside_fence = False
    started = False
    depth = 0
    body: list[str] = []
    for line in lines:
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            if started:
                body.append(line)
            continue
        heading = not inside_fence and line.startswith("#")
        if not started:
            if heading and "tier-2" in line.lower():
                started = True
                depth = len(line) - len(line.lstrip("#"))
            continue
        if heading and (len(line) - len(line.lstrip("#"))) <= depth:
            break
        body.append(line)
    assert started, (
        "CONTRIBUTING.md has no heading about the tier-2 run. CI does not run "
        "that suite; if the document does not say who does, nobody does."
    )
    return "\n".join(body)


def _obligation_block() -> str:
    """The bullets that say when the run is owed — not the whole section.

    Narrower than the section on purpose. `renderers/` is also named a
    paragraph earlier, where the text explains what else crosses that layer, so
    a check over the whole section stays green after the obligation itself
    stops mentioning it — which is the change that would actually cost a
    release.
    """
    lines = _tier2_section().splitlines()
    for index, line in enumerate(lines):
        if line.rstrip().endswith("You owe the run:"):
            block = []
            for following in lines[index + 1 :]:
                if not following.strip() or following.startswith(("-", " ")):
                    block.append(following)
                    continue
                break
            return "\n".join(block)
    raise AssertionError(
        "the tier-2 section no longer lists the moments the run is owed. "
        "An obligation with no list of occasions is a suggestion."
    )


def test_contributing_says_when_the_manual_run_is_owed():
    section = _tier2_section()
    assert TIER2.name in section, (
        "the tier-2 section does not name the module it is about. The suite is "
        "nobody's job unless the document says which suite."
    )
    owed = _obligation_block()
    for trigger in OWED_ON:
        assert trigger in owed, (
            f"the tier-2 section does not name {trigger!r} as a moment the run is "
            f"owed. 'Run it sometimes' is not an obligation — and dropping one "
            f"path from the list silently narrows what a release is protected "
            f"against."
        )


def test_the_section_reader_stops_at_the_next_heading_not_at_a_shell_comment():
    """The fence handling is the whole reason the check above reads the section.

    Moving the install block above the bullets is an ordinary edit to a
    document; without this, it truncated the section and turned the check red on
    text that was entirely correct.
    """
    section = _tier2_section()
    assert "```bash" in section, (
        "the tier-2 section no longer contains its command block — the reader "
        "is cutting the section short again."
    )
    assert f"pytest tests/{TIER2.name}" in section
