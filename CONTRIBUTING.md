# Contributing to TTRPG Session Transcriber

Thanks for your interest in contributing! This document covers how to get the project running locally and how to submit changes.

## Quick start

### Prerequisites

- Python 3.10, 3.11, or 3.12 (x64)
- Git
- ffmpeg (the installer downloads it automatically, but for development you may want it system-wide)
- Optional: NVIDIA GPU with CUDA 12.x for faster transcription

### Setup

```bash
git clone https://github.com/vvechkanov/ttrpg-session-transcriber.git
cd ttrpg-session-transcriber
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
pip install -e .[dev]
```

#### Linux: system libraries for Qt

`pip` installs PySide6's Python bindings but not the system libraries Qt links
against. Without them `import PySide6.QtGui` fails with
`ImportError: libEGL.so.1: cannot open shared object file`, which stops pytest
during startup — before a single test runs — because `pytest-qt` imports Qt
from its plugin hook. The test suite runs headless (`tests/conftest.py` sets
`QT_QPA_PLATFORM=offscreen`), but the offscreen platform plugin still needs
these:

```bash
sudo apt-get install -y libegl1 libxkbcommon0 libfontconfig1 libdbus-1-3 ffmpeg
```

This is the same list `.github/workflows/ci.yml` installs on its Ubuntu
runners; keep the two in sync. `ffmpeg` is there for
`tests/test_core_peaks.py`, which synthesises a sine-wave FLAC.

### Run the GUI

```bash
python -m ui
```

### Run tests

```bash
pytest tests/
```

### Lint and format

```bash
ruff check .
ruff format .
```

Settings live in `pyproject.toml` under `[tool.ruff]` — line length and rule
selection, shared by your checkout and CI.

The two are not the same check, though, and the difference is deliberate:

- **CI blocks on `ruff check --select F821 .`** — undefined names only. That
  one is clean today, so it never fails on code you did not touch.
- **`ruff check .`** applies the configured set and still reports findings
  inherited from before the linter was wired up. Fixing them is scheduled
  work; do not treat a non-zero count as something your change broke. CI runs
  this too, without blocking, and prints the count in the job summary.

There is no `pre-commit` setup here. An earlier version of this file said
`pre-commit install` would run these checks for you; it never could, because no
`.pre-commit-config.yaml` was ever committed. Run the two commands above
yourself before pushing.

`ruff format .` reformats to the 100-character line length above. The tree has
not been reformatted yet, so running it touches files beyond your own change —
keep those out of your commit until the one-off reflow lands.

## How to contribute

### Reporting bugs

Open an issue using the **Bug Report** template. Include:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your platform (Windows version, Python version, GPU model if relevant)
- Logs from the GUI launcher (the bottom log pane)

### Suggesting features

Open an issue using the **Feature Request** template. Before opening, please check the [TASKS.md](TASKS.md) roadmap — your idea may already be planned.

### Submitting code changes

1. **Fork** the repository and create a branch from `master`
2. **Make your change** — keep it focused, one logical change per PR
3. **Add tests** if you're adding code that should be tested. See `tests/` for examples.
4. **Run `ruff check .` and `pytest tests/`** locally before pushing
5. **Open a pull request** using the PR template
6. **Wait for CI** to pass. The maintainer will review the PR.

### Code style

- Python style is enforced by [ruff](https://docs.astral.sh/ruff/) (config in `pyproject.toml`)
- Line length: 100 characters
- Type hints encouraged but not yet required
- Docstrings: short and useful, not bureaucratic

### Commit messages

Conventional Commits style preferred:

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `test:` — adding or fixing tests
- `chore:` — tooling, dependencies, etc.

Example: `feat(asr): add SherpaOnnxBackend with GigaAM-v3 support`

## Architecture overview

See [TASKS.md](TASKS.md) for the high-level roadmap and the canonical design decisions. The short version:

- **`scripts/asr_backends/`** — pluggable ASR backends. All backends produce a canonical JSON contract documented in `base.py`.
- **`scripts/merge_whisperx.py`** — merges per-track transcripts into a unified timeline. Engine-agnostic — do not add Whisper-specific assumptions here.
- **`scripts/parse_fvtt_chat.py`** — converts Foundry VTT chat log into the same canonical JSON format so it can be merged with audio segments.
- **`launcher/`** — single-EXE installer (PyInstaller). Pure Python, dark-themed installer UI.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
