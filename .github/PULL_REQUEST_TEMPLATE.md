## Summary

What does this PR do? One or two sentences explaining the change.

## Motivation

Why is this change needed? Link to an issue if applicable.

Closes #

## Changes

- Change 1
- Change 2
- Change 3

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation only
- [ ] Refactor / cleanup (no functional change)
- [ ] Test infrastructure

## Test plan

How was this tested? What did you run?

- [ ] `ruff check --select F821 .` passes (the blocking gate; `ruff check .` still has known findings)
- [ ] `pytest tests/` passes
- [ ] Manually tested on a real Craig recording
- [ ] Manually tested on Windows
- [ ] Manually tested on Linux / macOS (if applicable)

## Checklist

- [ ] My code follows the project style (ruff)
- [ ] I have added tests for new functionality
- [ ] I have updated documentation where needed
- [ ] I have updated `CHANGELOG.md` under `[Unreleased]`
- [ ] My changes do not modify the source boundary — `sources/base.py` and the annotation types in `domain/annotations.py` (or if they do, the canonical contract every source returns is preserved)

## Screenshots

If this PR changes the GUI or installer, please include before/after screenshots.
