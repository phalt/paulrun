# Spec: rundot 0.7.0

Status: approved (2026-11-13)
Version target: 0.7.0

This builds on [SPEC-0.6.0.md](SPEC-0.6.0.md), [SPEC-0.3.0.md](SPEC-0.3.0.md), [SPEC-0.2.0.md](SPEC-0.2.0.md) and [SPEC.md](SPEC.md). Anything not mentioned here is unchanged.

## Objective

Runs that can stop part way and pick up where they left off, for people and for agents.

Two features:

1. **Resume.** A run that stops part way, because a block failed, a confirm was answered no or Ctrl-C was pressed, can be picked up at the step it stopped in. The steps before it aren't run again.
2. **`--no-input` and `--json`.** rundot never asks a question, and can print its events as JSON lines, so an agent or a CI job can run a runbook. When a run needs human input, for a `confirm` or an `input` block, it stops, and the next run carries on from there.

The runbook format doesn't change.

**User:** Paul, and agents or CI jobs running Paul's runbooks.

### User stories

- As Paul, when a release fails at step 4 of 5, I fix the problem, run the same command again and answer `r`, and only steps 4 and 5 run.
- As Paul, I can start over instead, with `s` at the question or with `--restart`.
- As Paul, I'm told if the runbook has changed since the run I'm resuming.
- As an agent, I run `VERSION=1.2.0 rundot release.md --no-input` and nothing waits for an answer. A missing input fails at once and names every input I need to set.
- As an agent, when the run reaches a `confirm`, it stops with exit code 3 and tells me what a person has to do. Once they've done it, I run the same command again and the run carries on after the confirm.
- As an agent, `--json` gives me one JSON object per line, so I can read each step, each line of output and how the run finished without parsing boxes.

## Decisions

1. **Resume starts at the beginning of the step the run stopped in,** not at the block that failed. Steps are what Paul sees and thinks in. The one exception is a run stopped by `--no-input` at a `confirm` or `input` block: it carries on at that block (decision 12).
2. **Run state is kept outside the project,** in `$XDG_STATE_HOME/rundot/runs/`, or `~/.local/state/rundot/runs/` when that's unset or empty. Nothing is written to the repository.
3. **A run is identified by its runbook and its directory:** the resolved runbook path and the resolved directory blocks run in. The same book run in two projects keeps two states.
4. **State is written as the run goes,** so a run killed outright can still be resumed. It's deleted when the run finishes `ok`. Dry runs never read or write state.
5. **Secrets are never saved.** They're asked for again on resume, or read from the environment as usual. Plain values are saved, from the frontmatter and from `input` blocks.
6. **On resume, the environment still comes first,** then saved values, then asking. A saved value is checked against the input's `pattern` and `choices` like any other.
7. **A changed runbook warns but still resumes.** If a step that's about to be skipped has changed, or the step being resumed has a different name, rundot says which and still offers to resume. If the runbook now has fewer steps than the one being resumed, it can't resume and starts over.
8. **Interactively, rundot asks before resuming,** with no default: `[r]esume / [s]tart over / [q]uit`. `--resume` resumes without asking, and is an error if there's nothing to resume. `--restart` deletes the state and starts over.
9. **`--no-input` never asks anything.** `Start?` is taken as yes, inputs come from the environment, saved state or their `default`, and stepping is off.
10. **`--no-input` resumes by itself** when there's state, whatever stopped the run, and says so, so an agent can fix a failure and run the same command again. `--restart` starts over. Paul chose this (2026-11-13).
11. **A missing frontmatter input under `--no-input` fails before anything runs,** naming every missing input, not just the first. Exit 1.
12. **Under `--no-input`, a `confirm` or an `input` block with no value stops the run with exit code 3,** which means "human input is needed". The state points at that block. The next run, when it resumes, treats the confirm as answered yes, or reads the input from the environment. Exit code 2 isn't used, since Click already uses it for usage errors. Paul chose the name `needs_human_input` over `needs_person`, `paused` and `waiting` (2026-11-13).
13. **`--json` implies `--no-input`,** since a prompt would put text that isn't JSON on stdout.
14. **Under `--json`, stdout is JSON lines only.** Errors still go to stderr as text. The transcript is unchanged.
15. **Flags that contradict each other are a usage error** (exit 2): `--no-input` with `--step`, `--resume` with `--restart`, and `--dry` with `--resume`, `--restart`, `--no-input` or `--json`.
16. No new runtime dependencies.

## Resume

### The state file

`<state dir>/<key>.json`, where `<key>` is the first 16 hex characters of the SHA-256 of `<resolved runbook path>\n<resolved directory>`. The file is created with mode `0600`.

```json
{
  "version": 1,
  "runbook": "/home/you/Projects/my-package/RELEASING.md",
  "directory": "/home/you/Projects/my-package",
  "started_at": "2026-11-13T14:02:11+00:00",
  "stopped": "failed",
  "step": 3,
  "block": 0,
  "steps": [
    {"name": "Run the tests", "hash": "9f2c…"},
    {"name": "Bump the version", "hash": "41ab…"},
    {"name": "Tag and push", "hash": "c07e…"},
    {"name": "Publish", "hash": "e5d1…"},
    {"name": "Announce", "hash": "88f0…"}
  ],
  "inputs": {"VERSION": "1.2.0", "PR": "42"}
}
```

- `step` is the index of the step to resume at, counting from 0. `block` is the index of the block in it to start at: 0, unless the run stopped under `--no-input` at a `confirm` or `input` block (decision 12).
- `stopped` is how the run stopped: `failed`, `aborted`, `interrupted`, `needs_human_input` or `running`. `running` means it was still going when the file was last written, e.g. the process was killed.
- A step's `hash` is the SHA-256 of its name and every block's language, kind and content, in order.
- `inputs` holds plain values only. A secret's name is never a key.
- A state file that can't be read, or has another `version`, is ignored with a warning, as if there were none.

When it's written:

- When each step starts: `step` is that step, `block` 0, `stopped` `running`.
- When an `input` block is answered: its value is added to `inputs`, unless it's secret.
- When the run stops part way: `stopped` is set.
- When the run finishes `ok`: the file is deleted.
- A run aborted at `Start?` hasn't started, so no file is written, and an existing one is left as it was.

### Resuming interactively

```
$ rundot RELEASING.md
Last run stopped at 4/5 Publish: failed (exit 1), 2026-11-13 14:02.
[r]esume / [s]tart over / [q]uit: r
PUBLISH_TOKEN (Token for the package index):
╭─ Release my-package ────────────────────────╮
│ directory  /home/you/Projects/my-package    │
│ resuming   4/5 Publish                      │
│ inputs     VERSION=1.2.0 PUBLISH_TOKEN=**** │
│ steps      1. Run the tests       done      │
│            2. Bump the version    done      │
│            3. Tag and push        done      │
│            4. Publish                       │
│            5. Announce                      │
│ blocks     2 run blocks                     │
╰─────────────────────────────────────────────╯
Start? [y/N] y

4/5  Publish ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

- The question comes after the runbook is checked and before inputs are collected. It loops until the answer is `r`, `s` or `q`. `q` exits 1 and leaves the state alone. `s` deletes it and runs from the start.
- The overview gets a `resuming` line, and the steps already done are marked `done` in dim. `blocks` counts only the run blocks that will run.
- Steps already done aren't shown again as rules.
- A changed runbook (decision 7) adds a yellow warning before the question, e.g. `RELEASING.md has changed since that run: "Tag and push" is different.`

### The transcript

A resumed run is recorded like any run, with one extra header line:

```
--- rundot RELEASING.md @ 2026-11-13T14:20:03+00:00
--- resumed at "Publish", from the run at 2026-11-13T14:02:11+00:00
--- inputs: VERSION=1.2.0 PUBLISH_TOKEN=****
```

## `--no-input`

| What rundot would ask | With `--no-input` |
|---|---|
| Resume, start over or quit | Resumes, and prints `resuming at 4/5 Publish`. |
| A frontmatter input | Environment, then saved state, then `default`. Otherwise it fails before anything runs: `missing inputs: VERSION, BRANCH. Set them in the environment.` Exit 1. |
| `Start? [y/N]` | Yes. |
| `Run this block?` | Never asked: stepping is off, even with `step: true` in the runbook. |
| A `confirm` block | Stops the run: `needs human input: Publish the GitHub release notes for v1.2.0. Run again once it's done.` Exit 3. On resume, it's taken as answered yes. |
| An `input` block | Environment, then saved state, then `default`. Otherwise it stops the run: `needs human input: set PR (The number GitHub gave the pull request) and run again.` Exit 3. |

A value from the environment or state that doesn't fit the input's `pattern` or `choices` fails as it does today, exit 1.

`--no-input` can also be set with `RUNDOT_NO_INPUT=1`, for CI jobs that run rundot through scripts they don't control. Any other value, including empty, leaves it off. Paul chose to have it (2026-11-13).

## `--json`

One JSON object per line on stdout, one per runner event, as it happens. Every object has `event` and `at` (ISO 8601 with milliseconds). Secrets are `****`, as everywhere else.

```json
{"event": "overview", "at": "…", "title": "Release my-package", "directory": "/home/you/Projects/my-package", "inputs": {"VERSION": "1.2.0", "PUBLISH_TOKEN": "****"}, "steps": ["Run the tests", "Bump the version", "Tag and push", "Publish", "Announce"], "resuming_at": 3}
{"event": "step_started", "at": "…", "number": 4, "name": "Publish"}
{"event": "block_started", "at": "…", "line": 41, "language": "sh", "code": "uv publish --token \"$PUBLISH_TOKEN\""}
{"event": "output", "at": "…", "text": "Uploading rundot-0.7.0.whl", "stderr": false}
{"event": "block_finished", "at": "…", "line": 41, "exit_code": 0, "duration": 1.2}
{"event": "confirm", "at": "…", "line": 50, "text": "Publish the GitHub release notes for v1.2.0."}
{"event": "run_finished", "at": "…", "status": "needs_human_input", "step": "Announce", "exit_code": null, "duration": 3.4}
```

| `event` | From | Fields besides `event` and `at` |
|---|---|---|
| `overview` | `Overview` | `title`, `directory`, `inputs`, `steps`, `resuming_at` (step index, or `null`) |
| `step_started` | `StepStarted` | `number` (from 1), `name` |
| `docstring` | `Docstring` | `line`, `text` |
| `confirm` | `Confirm` | `line`, `text` |
| `confirm_answered` | `ConfirmAnswered` | `line`, `yes` |
| `input_block` | `InputBlock` | `line`, `name`, `description` |
| `input_collected` | `InputCollected` | `line`, `name`, `value` |
| `block_started` | `BlockStarted` | `line`, `language`, `code` |
| `block_skipped` | `BlockSkipped` | `line` |
| `output` | `OutputLine` | `text`, `stderr` |
| `block_finished` | `BlockFinished` | `line`, `exit_code`, `duration` |
| `run_finished` | `RunFinished` | `status`, `step` (name, or `null`), `exit_code`, `duration` |

- `line` is the block's line in the runbook, so an agent can point at it.
- `status` is `ok`, `failed`, `aborted`, `interrupted` or `needs_human_input`.
- `check` problems that stop a run go to stderr as text, as today, and nothing is printed on stdout.
- Adding a field later isn't a breaking change. Removing or renaming one is.

## Commands (CLI)

```
rundot RUNBOOK [--dry] [--step | --no-step] [--show-code] [--resume | --restart] [--no-input] [--json]
rundot run [RUNBOOK] …the same options…
```

- `--resume`: resume without asking. Error (exit 1) if there's no state for this runbook and directory.
- `--restart`: delete any state and start from the first step.
- `--no-input`: never ask anything. See [`--no-input`](#--no-input).
- `--json`: print events as JSON lines. Implies `--no-input`.
- `rundot run` with no runbook, the picker, is a usage error with `--no-input` or `--json`, since picking is asking.

Exit codes: 0 success, 1 failure, 2 usage error, **3 human input is needed** (new).

## Runner changes

So the design can be checked against the code:

- `runner.run` takes a `start: tuple[int, int] = (0, 0)` (step, block) and a `saved: Mapping[str, str]` of plain values used after the environment. Steps before `start` aren't sent or run.
- `RunFinished.status` gains `needs_human_input`.
- The `Prompter` protocol is unchanged. `--no-input` is a new prompter, and it raises a `NeedsHumanInput` exception from `confirm` and `ask`, which the runner turns into `RunFinished("needs_human_input", …)`. `Start?` never reaches it, since the runner is told not to ask under `--no-input`.
- Run state is a new module, `rundot/state.py`: a listener on the runner's events, like `Transcript`, plus reading, matching and deleting state files.
- `--json` is a new sink in place of `_Printer`.

## Documentation

- `docs/cli.md`: the new flags, exit code 3, and a "Running from an agent or CI" section.
- `docs/runbook-format.md`: a "Resuming a run" section, near the transcript.
- `README.md`: the "Agents improvise. Runbooks don't." section mentions `--no-input` and exit code 3.
- The agent prompt at rundot.dev/prompt.txt: run with `--no-input --json`, and on exit 3 hand the message to the person and run again. That file lives with the website, not in this repo.
- `CHANGELOG.md` and `docs/CHANGELOG.md`: a `## 0.7.0` section.

## Testing strategy

As the earlier specs, with 100% line and branch coverage.

- The state directory is always set to `tmp_path` in tests, through `XDG_STATE_HOME`. Tests never touch `~/.local/state`.
- Resume tested end to end with `CliRunner`: a fixture runbook whose third step fails until a file exists in `tmp_path`, run, then fixed, then resumed, checking which blocks ran.
- A test that no secret's value ever appears in a state file, including from a secret `input` block.
- Each `--json` event type tested by parsing every stdout line with `json.loads`.
- `--no-input` tested with `CliRunner` and no `input=`, so any prompt fails the test.
- New readable fixtures: `tests/runbooks/resume-example.md` and `tests/runbooks/needs-human-input-example.md`.

## Out of scope for 0.7.0

- `--from <step>`, to start at any step without a stopped run
- `--yes`, to answer confirms automatically
- Resuming at the failed block rather than its step
- Locking, so two runs of one book in one directory at once can't overwrite each other's state. The last to write wins.
- Listing or cleaning up old state files, e.g. `rundot runs`
- Saving a block's output for later blocks
- Turning on `--no-input` by itself when stdin isn't a terminal

## Success criteria

- [ ] A run that fails at step 4 of 5, rerun and answered `r`, runs only steps 4 and 5, and asks for secrets again
- [ ] `s` and `--restart` start from step 1 and delete the state; `q` exits 1 and keeps it
- [ ] A run that finishes `ok` leaves no state file; a `--dry` run never reads or writes one
- [ ] A run killed during step 3 resumes at step 3
- [ ] A runbook changed in a skipped step warns before resuming, and one with fewer steps starts over
- [ ] No secret's value is ever in a state file
- [ ] With `--no-input`, no prompt is ever shown; missing inputs are all named and exit 1
- [ ] With `--no-input`, a `confirm` exits 3 and the next run carries on after it; an `input` block with no value exits 3 and the next run with it set carries on from it
- [ ] With `--json`, every stdout line is valid JSON, and the events match the table
- [ ] The contradicting flags in decision 15 are usage errors
- [ ] Docs and changelog updated as listed

## Open questions

None.
