# 📟 Command line

```sh
rundot RUNBOOK [--dry] [--step | --no-step] [--show-code]      # run a runbook
rundot run RUNBOOK [--dry] [--step | --no-step] [--show-code]  # the same, in full
rundot check RUNBOOK                                           # find problems without running anything
rundot inputs RUNBOOK                                          # list the inputs a runbook needs
rundot library                                                 # list the books in your runbook library
rundot backends                                                # list the languages rundot can run
rundot --version
```

`rundot` on its own shows this list.

## Naming a runbook

`RUNBOOK` is a file, or the name of a book in your [runbook library](library.md):

```sh
rundot RELEASING.md        # the file RELEASING.md, here
rundot rebuild-frontend    # the book rebuild-frontend.md, in your library
```

1. If `RUNBOOK` is a file that exists, that's the runbook, so a file is never hidden by a book with the same name.
2. Otherwise, if it has no `/`, it's the book `<name>.md` in your library. The `.md` is optional.
3. Otherwise it's a usage error, which names both places rundot looked:

```
Error: Invalid value for 'RUNBOOK': no runbook 'rebuild-frontend': no such file here, and no rebuild-frontend.md in the library at /home/you/runbooks
```

## rundot run

Runs a runbook, step by step.

```sh
rundot RELEASING.md
```

You don't need to type `run`: anything after `rundot` that isn't a command is a runbook. Options go before or after it, so `rundot RELEASING.md --dry` is the same as `rundot --dry RELEASING.md`. Use `rundot run check` to run a book called `check.md`, since `rundot check` is the command.

1. **Checks the runbook**, as [`rundot check`](#rundot-check) does. Errors stop it here.
2. **Asks whether to resume**, if the last run of this runbook in this directory stopped part way. See [Resuming a run](#resuming-a-run).
3. **Collects the inputs**. See [Inputs](runbook-format.md#inputs).
4. **Shows the plan** and asks `Start? [y/N]`.
5. **Runs each step in order**, streaming each block's output as it's printed. Each block shows its language and when it started, then what it printed, then its exit code and how long it took. A line it wrote to stderr has a red `│`.

```
VERSION (The version to release, e.g. 1.2.0): 1.2.0
╭─ Release my-package ─────────────────────╮
│ directory  /home/you/Projects/my-package │
│ inputs     VERSION=1.2.0                 │
│ steps      1. Run the tests              │
│            2. Tag the release            │
│            3. Publish on GitHub          │
│ blocks     2 run blocks                  │
╰──────────────────────────────────────────╯
Start? [y/N] y

1/3  Run the tests ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌ sh · 10:02:13.482
  │ ...
  └ ✓ exit 0 · 4.2s

2/3  Tag the release ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌ sh · 10:02:17.705
  └ ✓ exit 0 · 0.1s

3/3  Publish on GitHub ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
╭─ confirm ───────────────────────────────╮
│ Create a GitHub release from tag 1.2.0. │
╰─────────────────────────────────────────╯
Continue? [y/N] y

╭───────────────────────╮
│ ✓ finished ok · 12.8s │
╰───────────────────────╯
transcript: logs/release-1.2.0.md
```

`directory` is where blocks will run. See [Where blocks run](runbook-format.md#where-blocks-run).

The run stops at the first block that fails:

```
1/1  Build ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌ sh · 10:02:13.482
  │ Building
  │ make: *** [build] Error 2
  └ ✗ exit 2 · 0.0s

╭─────────────────────────────────────╮
│ ✗ failed at "Build" (exit 2) · 0.0s │
╰─────────────────────────────────────╯
```

Only `y` answers `Start?` and `Continue?` with yes. Anything else, including enter, ends the run as aborted.

### --show-code

Shows each block's code above what it printed:

```
  ┌ sh · 10:02:13.482
  │ echo "Building"
  ├ output
  │ Building
  └ ✓ exit 0 · 0.0s
```

`--dry` always shows the code.

### Picking a book

With no runbook, `rundot run` asks which book from your library to run:

```
$ rundot run
  1. rebuild-frontend     Rebuild the frontend
  2. update-project-deps  Update a project's dependencies
Run which? (q to quit) 1
```

Answer with a number. `--dry` and `--step` work too. Answer `q`, or press enter, to stop without running anything.

### --dry

Shows what the runbook would do, without running anything.

```sh
rundot --dry RELEASING.md
```

- Every block is shown with its inputs filled in.
- There's no `Start?`, `confirm` blocks don't wait, and no transcript is written.
- Secrets and [input blocks](runbook-format.md#input-blocks) aren't asked for.

```
VERSION (The version to release, e.g. 1.2.0): 1.2.0
╭─ Release my-package ─────────────────────╮
│ directory  /home/you/Projects/my-package │
│ inputs     VERSION=1.2.0                 │
│ steps      1. Run the tests              │
│            2. Tag the release            │
│            3. Publish on GitHub          │
│ blocks     2 run blocks                  │
╰──────────────────────────────────────────╯
dry run: nothing will be run

1/3  Run the tests ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌ sh
  │ make test
  └ not run

2/3  Tag the release ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌ sh
  │ git tag 1.2.0
  └ not run

3/3  Publish on GitHub ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
╭─ confirm ───────────────────────────────╮
│ Create a GitHub release from tag 1.2.0. │
╰─────────────────────────────────────────╯

╭──────────────────────────╮
│ dry run, nothing was run │
╰──────────────────────────╯
```

### --step

Asks before running each `run` block.

```sh
rundot --step RELEASING.md
```

```
1/2  Build ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌ sh · 10:02:13.482
  ├ Run this block? [y]es / [s]kip / [q]uit y
  │ Building
  └ ✓ exit 0 · 0.0s

2/2  Publish ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌ sh · 10:02:13.486
  ├ Run this block? [y]es / [s]kip / [q]uit s
  └ ↷ skipped

╭──────────────────────╮
│ ✓ finished ok · 0.0s │
╰──────────────────────╯
```

`y` runs the block, `s` skips it, and `q` ends the run as aborted. The code isn't shown unless you add `--show-code`. With `--dry`, `--step` does nothing, since nothing runs.

A runbook that should always be run this way can set [`step: true`](runbook-format.md#frontmatter) in its frontmatter, so you don't need to remember `--step`. To run one of those straight through, pass `--no-step`.

### Pressing Ctrl-C

- A running block gets the Ctrl-C too, and rundot waits for it to stop.
- If a block ignores it, press Ctrl-C again to stop the block and everything it started.
- The run ends as `✗ interrupted at "<step>"`.

### Resuming a run

A run that stops part way, because a block failed, a `confirm` was answered no or you pressed Ctrl-C, can be picked up at the step it stopped in. Fix what went wrong, run the same command again, and answer `r`:

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

- `r` resumes: the steps already done are skipped, and the step it stopped in runs again from its start. Plain inputs are kept from the last run, but secrets are asked for again.
- `s` starts over from the first step, and forgets the stopped run.
- `q`, or Ctrl-C, runs nothing and keeps the stopped run for next time. rundot exits 1.

If a step the last run did has changed since, or the step it resumes at has a new name, rundot warns before asking, e.g. `RELEASING.md has changed since that run: "Tag and push" is different.` A runbook that now has fewer steps can't be resumed, so it starts over and says so. A stopped run is only ever resumed in the directory it ran in. See [Resuming a run](runbook-format.md#resuming-a-run) for what's kept, and where.

### --resume and --restart

`--resume` resumes without asking. It's an error, exit 1, if there's nothing to resume. `--restart` forgets any stopped run and starts from the first step. They can't be used together, or with `--dry`, which never reads or changes a stopped run.

### --no-input

rundot never asks anything, so an agent or a CI job can run a runbook:

```sh
VERSION=1.2.0 rundot RELEASING.md --no-input
```

| What rundot would ask | With `--no-input` |
|---|---|
| Resume, start over or quit | Resumes, and prints `resuming at 4/5 Publish`. `--restart` starts over instead. |
| A frontmatter input | The environment, then the stopped run, then its `default`. If any inputs are still missing, the run fails before anything runs and names every one: `missing inputs: VERSION, BRANCH. Set them in the environment.` Exit 1. |
| `Start? [y/N]` | Yes. |
| `Run this block?` | Never asked: stepping is off, even with `step: true` in the runbook. |
| A `confirm` block | Stops the run: `needs human input: Publish the GitHub release notes for v1.2.0. Run again once it's done.` Exit 3. The next run carries on after the confirm, as if it had been answered yes. |
| An `input` block | The environment, then the stopped run, then its `default`. Otherwise it stops the run: `needs human input: set PR (The number GitHub gave the pull request) and run again.` Exit 3. The next run, with it set, carries on from that block. |

A value from the environment or the stopped run that doesn't fit the input's `pattern` or `choices` fails, exit 1.

`RUNDOT_NO_INPUT=1` does the same as `--no-input`, for CI jobs that run rundot through scripts you don't control. Any other value, including an empty one, leaves it off.

`--no-input` can't be used with `--step` or `--dry`, or without a runbook, since picking a book is asking. Those are usage errors, exit 2, whether it's turned on by the flag or the variable.

### --json

Prints each of the run's events as one line of JSON on stdout, as it happens, so an agent can follow a run without reading boxes. `--json` implies [`--no-input`](#-no-input), since a prompt would put text that isn't JSON on stdout.

```json
{"event": "overview", "at": "2026-11-13T14:20:03.104+00:00", "title": "Release my-package", "directory": "/home/you/Projects/my-package", "inputs": {"VERSION": "1.2.0", "PUBLISH_TOKEN": "****"}, "steps": ["Run the tests", "Bump the version", "Tag and push", "Publish", "Announce"], "resuming_at": 3}
{"event": "step_started", "at": "2026-11-13T14:20:03.106+00:00", "number": 4, "name": "Publish"}
{"event": "block_started", "at": "2026-11-13T14:20:03.106+00:00", "line": 41, "language": "sh", "code": "uv publish --token \"$PUBLISH_TOKEN\"\n"}
{"event": "output", "at": "2026-11-13T14:20:03.512+00:00", "text": "Uploading rundot-0.7.0.whl", "stderr": false}
{"event": "block_finished", "at": "2026-11-13T14:20:04.307+00:00", "line": 41, "exit_code": 0, "duration": 1.201}
{"event": "step_started", "at": "2026-11-13T14:20:04.308+00:00", "number": 5, "name": "Announce"}
{"event": "confirm", "at": "2026-11-13T14:20:04.308+00:00", "line": 50, "text": "Publish the GitHub release notes for v1.2.0.\n"}
{"event": "run_finished", "at": "2026-11-13T14:20:04.309+00:00", "status": "needs_human_input", "step": "Announce", "exit_code": null, "duration": 1.205, "message": "Publish the GitHub release notes for v1.2.0. Run again once it's done."}
```

stdout is JSON lines only. Everything else rundot says, such as `check` problems, `resuming at`, `missing inputs` and `needs human input`, goes to stderr as text. The transcript is written as usual.

Every object has `event` and `at`, when it happened, in ISO 8601 with milliseconds. Secrets are `****`, as everywhere else.

| `event` | From | Fields besides `event` and `at` |
|---|---|---|
| `overview` | `Overview` | `title`, `directory`, `inputs`, `steps`, `resuming_at` (the index of the step a resumed run starts at, or `null`) |
| `step_started` | `StepStarted` | `number` (from 1), `name` |
| `docstring` | `Docstring` | `line`, `text` |
| `confirm` | `Confirm` | `line`, `text` |
| `confirm_answered` | `ConfirmAnswered` | `line`, `yes` |
| `input_block` | `InputBlock` | `line`, `name`, `description` |
| `input_collected` | `InputCollected` | `line`, `name`, `value` |
| `block_started` | `BlockStarted` | `line`, `language`, `code` |
| `block_skipped` | `BlockSkipped` | `line` |
| `output` | `OutputLine` | `text`, `stderr` |
| `block_finished` | `BlockFinished` | `line`, `exit_code`, `duration` (seconds) |
| `run_finished` | `RunFinished` | `status`, `step` (its name, or `null`), `exit_code`, `duration`, `message` (what a person has to do, or `null`) |

- `line` is the block's line in the runbook, so an agent can point at it.
- `status` is `ok`, `failed`, `aborted`, `interrupted` or `needs_human_input`.
- A field may be added in a later version. One is never removed or renamed without a major version.

`--json` can't be used with `--dry` or `--step`, or without a runbook. Those are usage errors, exit 2.

## rundot check

Finds problems in a runbook without running anything.

```sh
rundot check RELEASING.md
```

```
RELEASING.md: ok
```

Each problem is shown with its line, so your editor can jump to it:

```
broken.md:6: error: input VERSION is declared twice (first on line 4)
broken.md:8: warning: input BRANCH is never used
broken.md:12: error: run blocks must be inside a step (a ## heading)
broken.md:19: error: <TAG> isn't a declared input
broken.md:21: error: syntax error near unexpected token `fi'

4 errors, 1 warning
```

**Errors** stop the runbook running:

- a missing `title`, or a frontmatter value of the wrong type
- an input without a `name` or `description`, a name that isn't UPPER_SNAKE_CASE or is declared twice, or a `pattern` that isn't a valid regular expression
- a `default` or `choices` that can't work. See [Defaults](runbook-format.md#defaults) and [Choices](runbook-format.md#choices).
- a placeholder that isn't a declared input, or a secret used as a placeholder
- an `input` block that isn't valid YAML, or is used before it's asked for
- a block before the first `##` heading
- a `run` block in a language no backend runs, or a `python` command that isn't installed
- a syntax error in a shell or Python block

**Warnings** don't:

- a frontmatter or input key rundot doesn't know, often a typo
- an input nothing uses
- a Python `SyntaxWarning`, and [shellcheck](install.md#optional-shellcheck) findings if it's installed

## rundot inputs

Lists the inputs a runbook needs, so you know what to have ready.

```sh
rundot inputs PUBLISHING.md
```

```
VERSION  The version being released, e.g. 1.2.0
         pattern: ^\d+\.\d+\.\d+$
BRANCH   The branch to release from
         default: main
PR       The number GitHub gave the pull request
         pattern: ^\d+$
         asked in "Open the pull request"
OTP      The code from your authenticator app
         pattern: ^\d{6}$
         secret
         asked in "Publish"
```

Inputs from [input blocks](runbook-format.md#input-blocks) come last, with the step that asks for them. Frontmatter inputs are listed even if the rest of the runbook is broken.

## rundot library

Lists the books in your [runbook library](library.md), with each one's `title` and `description`.

```
$ rundot library
library: /home/you/runbooks
rebuild-frontend     Rebuild the frontend
                     Clean install the frontend's dependencies, then rebuild it.
update-project-deps  Update a project's dependencies
```

A book whose frontmatter can't be read is still listed, with why.

## rundot backends

Lists the languages rundot can run, and the package each comes from.

```
$ rundot backends
python  python, py       rundot.backends.python:PythonBackend (rundot 0.2.0)
shell   sh, bash, shell  rundot.backends.shell:ShellBackend (rundot 0.2.0)
```

## Running from an agent or CI

Run with `--no-input --json`, and set the runbook's inputs in the environment:

```sh
VERSION=1.2.0 rundot RELEASING.md --no-input --json
```

Nothing waits for an answer. Read stdout line by line for what's happening, and the exit code for how it ended:

- **0**: the run finished.
- **1**: something failed. stderr says what, e.g. a failed block or missing inputs. Fix it and run the same command again: the run resumes at the step that failed.
- **3**: a person has to do something, such as a `confirm` step or setting an input. Hand them the `needs human input:` line from stderr, which is also `message` in the last JSON line. Once they've done it, run the same command again, and the run carries on from there.

`--restart` starts from the first step instead of resuming.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The run finished, or `check` found no errors. |
| `1` | A block failed, the run was aborted or interrupted, `check` found errors, inputs were missing under `--no-input`, or the runbook couldn't be read. |
| `2` | The command was used wrongly, e.g. a runbook that doesn't exist, or flags that can't be used together, such as `--dry` with `--resume`. |
| `3` | Human input is needed: the run stopped under `--no-input` at a `confirm`, or at an `input` block with no value. Run again once it's done. |
