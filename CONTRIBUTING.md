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

### Run the GUI

```bash
python -m ui
```

### Run tests

```bash
pytest tests/
```

### Lint and format

> **Not wired up yet.** There is no ruff configuration in `pyproject.toml`, no `lint`
> job in CI, and no `pre-commit` config in the repository. Making ruff a blocking gate
> (including automated layer-boundary checks) is a planned task — see `TASKS.md` §4.2.
> Until then, match the style of the surrounding code.

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
4. **Run `pytest tests/`** locally before pushing
5. **Open a pull request** using the PR template
6. **Wait for CI** to pass. The maintainer will review the PR.

### Code style

- Python style follows [ruff](https://docs.astral.sh/ruff/) defaults; the config and the
  blocking CI gate are still to be added (`TASKS.md` §4.2)
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

See [ARCHITECTURE.md](ARCHITECTURE.md) for layers, contracts and ADRs, [TASKS.md](TASKS.md)
for the plan of work, and [VISION.md](VISION.md) for the product specification. The short
version — six layers, imports point one way only:

- **`domain/`** — pure dataclasses: annotations, timeline, script events, speaker map. Imports nothing from the project.
- **`sources/`** — anything that produces annotations with timestamps: ASR backends (`speech/`), Foundry VTT chat and combat dumps (`game_log/`). All speech backends produce the same canonical JSON contract.
- **`mergers/`** — combine a `Timeline` into one ordered list of script events. Engine-agnostic — do not add Whisper-specific assumptions here.
- **`renderers/`** — format script events into the output artifact (`merged.txt` today).
- **`core/`** — orchestration: discovery, pipeline stages, chunking, GPU pre-flight, backend installers.
- **`ui/`** — PySide6/QML app (`ui/qml`, `ui/models`, `ui/engines`) plus the CLI (`ui/cli.py`).
- **`launcher/`** — single-EXE bootstrap installer (PyInstaller). Pure Python, dark-themed installer UI. Frozen — see FEATURE_REQUESTS.md #1.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
