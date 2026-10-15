# Implementation Plan: paulrun 0.3.0

Status: approved (2026-10-15)
Spec: [specs/SPEC-0.3.0.md](../specs/SPEC-0.3.0.md)
Tasks: [tasks/todo-0.3.0.md](todo-0.3.0.md)

## Overview

Two small, independent changes: a `step` frontmatter key with a `--no-step` flag to override it, and `q` to quit the book picker.

## Architecture decisions

- **The runner doesn't change.** It already takes `step_by_step`. `runbook.parse` reads `step` into `Runbook.step`, and `cli.py` decides: `--step/--no-step` is a Click flag pair with `default=None`, so "not given" is `None`, and then `parsed.step` is used.
- **`step` is parsed like `secret`:** anything truthy is `True`, so a malformed value can only make a run ask more. Validation reports anything that isn't a YAML boolean.
- **`q` is handled in `_pick`,** alongside the blank answer, before the number check.

## Task list

Full task bodies are in [todo-0.3.0.md](todo-0.3.0.md).

- [x] Task 1: `step` in the frontmatter, and `--no-step`
- [x] Task 2: `q` to quit the picker

### Checkpoint: Ready to release (Paul only)
- [x] Paul approves the spec's format change (approved 2026-10-15)
- [ ] Paul releases paulrun 0.3.0 with `PUBLISHING.md`

Agents never publish to PyPI or deploy docs (SPEC.md Boundaries).

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `skipped (--step)` becoming `skipped` changes the transcript format, and anything that greps old transcripts | Low | The CHANGELOG says so. The old wording would be wrong for a block skipped under `step: true` |
| `step: "true"` (quoted) looks right but is a string | Low | `check` errors on it. If run anyway it's truthy, so it steps, which is what was meant |
