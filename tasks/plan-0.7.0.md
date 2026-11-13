# Implementation Plan: rundot 0.7.0

Status: approved (2026-11-13)
Spec: [specs/SPEC-0.7.0.md](../specs/SPEC-0.7.0.md)
Tasks: [tasks/todo-0.7.0.md](todo-0.7.0.md)

## Overview

Teach the runner to start part way through a runbook and to stop for human input. Then add a state module that records where a run got to, and wire resume, `--no-input` and `--json` into the CLI.

## Architecture decisions

- **The runner learns two things and nothing else.**
  - `run(..., start=(step, block), saved={...})`. Steps before `start` aren't sent or run. `saved` holds plain values, used after the environment and before asking.
  - A new status, `needs_human_input`, which a prompter raises as `NeedsHumanInput`.
  - It knows nothing about state files, JSON or `--no-input`.
- **A confirm at `start` counts as answered yes.** When the run resumes at a `confirm` block, the runner sends `ConfirmAnswered(yes=True)` without asking, so the transcript records it. An `input` block at `start` is collected as usual: environment, then saved, then asking.
- **`Overview` gains `resuming_at: int | None`.** The printer marks earlier steps `done`, and the transcript adds its `--- resumed at` line. `run_blocks` counts only the blocks that will run.
- **`Start?` is skipped through a flag,** `run(..., ask_to_start=False)`, rather than by the prompter answering it. Then the `--no-input` prompter can raise on every question it gets.
- **Run state is `rundot/state.py`:**
  - `RunState`, a dataclass, with `load()`, `save()` and `delete()`.
  - `key(runbook, cwd)` and `step_hash(step)`.
  - `StateRecorder`, a listener on runner events, like `Transcript`. It writes on `StepStarted`, on `InputCollected` for plain values, and on `RunFinished`.
  - Files are written to a temporary file and renamed, so a killed run never leaves half a file. They're created with mode `0600`.
  - The state directory comes from the environment passed in, not read globally, so tests can point it at `tmp_path`.
- **JSON lines are `rundot/jsonlines.py`:** one `to_json(event, at) -> dict` per event type, and a sink that writes `json.dumps(...)` lines. A `match` on the event types keeps it exhaustive, and `ty` catches a missed one.
- **Missing inputs are checked up front in the CLI.** Under `--no-input`, before `runner.run`, the CLI lists every frontmatter input with no environment value, no saved value and no default. If there are any, it fails naming all of them. The runner's one-by-one collection never sees a missing input.
- **Layers:** `rundot.state` and `rundot.jsonlines` join `rundot.transcript`'s layer in the import-linter contract. They depend on `runner` and `runbook`, and only `cli` imports them.
- **The prompt for resuming lives in the CLI,** as the book picker does. `ClickPrompter` gains nothing new.
- No new runtime dependencies. `hashlib`, `json`, `os` and `tempfile` are enough.

## Task list

Full task bodies are in [todo-0.7.0.md](todo-0.7.0.md).

Tasks 1–2 change the runner, 3 adds the state module, 4–6 wire in the CLI, and 7 covers docs. Each task leaves `main` releasable: until task 4, nothing user-visible changes.

1. Runner: start part way, with saved values
2. Runner: `needs_human_input`
3. Run state module
4. Resume in the CLI
5. `--no-input` and `RUNDOT_NO_INPUT`
6. `--json`
7. Docs and changelog

## Risks

- **Ctrl-C while state is being written.** Mitigated by writing a temporary file and renaming it.
- **Reading resume state from the wrong project.** The key uses resolved paths, so symlinks and `..` can't split or merge runs. Tested with a symlinked folder.
- **JSON field drift.** Each event type has one test that pins its fields, so renaming a field fails a test.
