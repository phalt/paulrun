# rundot 0.7.0 tasks

Plan: [tasks/plan-0.7.0.md](plan-0.7.0.md). Spec: [specs/SPEC-0.7.0.md](../specs/SPEC-0.7.0.md).

Every task is done test-first, in red-green slices, and also clears the standing bar:
- `make format`, `make ty`, `make lint-imports` and `make test` are clean, with 100% line and branch coverage
- the `## 0.7.0` section of `CHANGELOG.md`, copied to `docs/CHANGELOG.md`, covers anything user-visible
- no test reads or writes the real `~/.local/state`

---

## Task 1: Runner starts part way, with saved values

**Description:** `runner.run` takes `start: tuple[int, int] = (0, 0)` and `saved: Mapping[str, str] = {}`. Steps before `start[0]` and blocks before `start[1]` are neither sent nor run. A `confirm` at `start` is answered yes without asking. `Overview` gains `resuming_at`. Inputs are collected from the environment, then `saved`, then by asking. Also add `ask_to_start: bool = True`.

**Acceptance criteria:**
- [x] With `start=(2, 0)`, only steps 3 onwards are sent, and `Overview.resuming_at == 2`
- [x] `Overview.run_blocks` counts only the blocks that will run
- [x] With `start` at a confirm, `ConfirmAnswered(yes=True)` is sent and the prompter isn't asked
- [x] A saved value is used when the environment has none, and is checked against `pattern` and `choices`
- [x] The environment wins over a saved value; secrets are never taken from `saved`
- [x] `ask_to_start=False` doesn't ask `Start?`
- [x] With the defaults, behaviour is unchanged (existing tests pass untouched)

**Files likely touched:** `rundot/runner.py`, `rundot/inputs.py` (`collect` takes `saved`), `tests/test_runner.py`, `tests/test_inputs.py`

**Dependencies:** None

## Task 2: Runner stops for human input

**Description:** Add `NeedsHumanInput` to `rundot/inputs.py`, next to `Prompter`. When a prompter raises it from `confirm` or `ask` during a step, the run finishes as `RunFinished("needs_human_input", …, step)`. The message says what's needed. Add `needs_human_input` to the transcript's `--- finished:` line.

**Acceptance criteria:**
- [x] Raised at a `confirm`, the run finishes `needs_human_input` at that step, with the block it stopped at
- [x] Raised at an `input` block, the same
- [x] The transcript records `--- finished: needs human input at "<step>"`
- [x] `RunFinished` carries the block it stopped at, `block: Block | None`, so the state can point at it

**Files likely touched:** `rundot/inputs.py`, `rundot/runner.py`, `rundot/transcript.py`, matching tests

**Dependencies:** Task 1

## Task 3: Run state module

**Description:** `rundot/state.py` with `state_dir(env)`, `key(runbook_path, cwd)`, `step_hash(step)`, `RunState` (load, save, delete) and `StateRecorder`, a listener on runner events. Add it to the import-linter layers.

**Acceptance criteria:**
- [x] `state_dir` is `$XDG_STATE_HOME/rundot/runs`, or `~/.local/state/rundot/runs` when that's unset or empty
- [x] `key` is the same for a path and its symlink, and different for two directories
- [x] `step_hash` changes when a step's name or any block's language, kind or content changes
- [x] `StateRecorder` writes `running` at each `StepStarted`, adds plain `InputCollected` values, writes the stop reason, step and block at `RunFinished`, and deletes the file on `ok`
- [x] A run that's aborted before its first step writes nothing and leaves an existing file alone
- [x] No secret's value is ever in the file, including from a secret `input` block
- [x] Files are mode `0600` and written by renaming a temporary file
- [x] A file that can't be parsed, or has another `version`, loads as `None` with a warning

**Files likely touched:** `rundot/state.py`, `pyproject.toml` (import-linter layers), `tests/test_state.py`

**Dependencies:** Task 2

## Task 4: Resume in the CLI

**Description:** Wire `StateRecorder` into `run_runbook`. Before collecting inputs, if there's state, ask `[r]esume / [s]tart over / [q]uit`. Add `--resume` and `--restart`. Warn about a changed runbook. Show `resuming` and `done` in the overview, and add the `--- resumed at` line to the transcript.

**Acceptance criteria:**
- [ ] End to end: a runbook whose step 3 fails until a file exists fails, then, once the file exists, resumes at step 3 on `r`, and steps 1–2 don't run
- [ ] `s` and `--restart` start at step 1 and delete the state; `q` exits 1 and keeps it
- [ ] `--resume` with no state exits 1 with a clear message
- [ ] Secrets are asked for again on resume
- [ ] A changed skipped step gives a yellow warning; a runbook with fewer steps starts over and says so
- [ ] `--dry` never reads or writes state; `--dry` with `--resume` or `--restart` is a usage error, and so is `--resume` with `--restart`
- [ ] The overview shows `resuming n/total Name` and marks earlier steps `done`; the transcript has `--- resumed at "<step>", from the run at <time>`

**Files likely touched:** `rundot/cli.py`, `rundot/transcript.py`, `tests/test_cli.py`, `tests/test_transcript.py`, `tests/runbooks/resume-example.md`

**Dependencies:** Task 3

## Task 5: `--no-input`

**Description:** A `NoInputPrompter` that raises `NeedsHumanInput` with the spec's messages. `--no-input`, or `RUNDOT_NO_INPUT=1`, uses it, passes `ask_to_start=False`, turns stepping off, resumes by itself when there's state, and checks for missing inputs up front. Exit code 3 for `needs_human_input`.

**Acceptance criteria:**
- [ ] Tested with `CliRunner` and no `input=`: no prompt is ever shown
- [ ] Missing frontmatter inputs are all named in one error, exit 1, before anything runs; defaults and saved values count as present
- [ ] A `confirm` exits 3 with `needs human input: <first line>`; the next run resumes after it and records `confirm: … -> yes`
- [ ] An `input` block with no value exits 3; the next run, with the value set, resumes at it
- [ ] With state from a failed run, `--no-input` resumes by itself and prints `resuming at n/total Name`
- [ ] `RUNDOT_NO_INPUT=1` acts like the flag; any other value doesn't
- [ ] `--no-input` with `--step`, or with `--dry`, is a usage error; the picker with `--no-input` is a usage error
- [ ] `step: true` in the runbook is ignored under `--no-input`

**Files likely touched:** `rundot/cli.py`, `tests/test_cli.py`, `tests/runbooks/needs-human-input-example.md`

**Dependencies:** Task 4

## Task 6: `--json`

**Description:** `rundot/jsonlines.py` turns each runner event into the dict in the spec's table, with `event` and `at`. `--json` uses it as the sink in place of `_Printer`, and implies `--no-input`. Every other message (`resuming at`, `needs human input`, the transcript path) goes to stderr under `--json`.

**Acceptance criteria:**
- [ ] One test per event type pins its fields exactly
- [ ] End to end, every stdout line parses with `json.loads`, and nothing else is on stdout
- [ ] `check` problems go to stderr and nothing goes to stdout
- [ ] Secrets are `****` in every field
- [ ] `--json` without `--no-input` still never asks anything
- [ ] `--json` with `--dry` is a usage error

**Files likely touched:** `rundot/jsonlines.py`, `rundot/cli.py`, `pyproject.toml` (import-linter layers), `tests/test_jsonlines.py`, `tests/test_cli.py`

**Dependencies:** Task 5

## Task 7: Docs and changelog

**Acceptance criteria:**
- [ ] `docs/cli.md`: `--resume`, `--restart`, `--no-input`, `--json`, `RUNDOT_NO_INPUT`, exit code 3, and a "Running from an agent or CI" section
- [ ] `docs/runbook-format.md`: a "Resuming a run" section near the transcript
- [ ] `README.md`: the agents section mentions `--no-input` and exit code 3
- [ ] `CHANGELOG.md` and `docs/CHANGELOG.md` have a `## 0.7.0` section
- [ ] A note for Paul on what to change in rundot.dev/prompt.txt, which isn't in this repo

**Files likely touched:** `docs/cli.md`, `docs/runbook-format.md`, `README.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Dependencies:** Tasks 1–6
