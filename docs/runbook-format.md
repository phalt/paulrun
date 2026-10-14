# 📜 Runbook format

A runbook is a markdown file. Frontmatter at the top sets it up, each `##` heading is a step, and code blocks marked for paulrun are shown, paused on, or run. Everything else is documentation.

Run `paulrun check` on a runbook to find anything wrong with it.

## Frontmatter

YAML between `---` lines at the top of the file:

```yaml
---
title: Release my-package                    # required
description: Release a new version.          # optional
output_path: logs/release-<VERSION>.md       # optional
python: uv run python                        # optional
inputs:                                      # optional
  - name: VERSION                            # required
    description: The version to release, e.g. 1.2.0   # required
    pattern: '^\d+\.\d+\.\d+$'               # optional
  - name: PUBLISH_TOKEN
    description: Token for the package index
    secret: true                             # optional, default false
---
```

| Key | What it does |
|---|---|
| `title` | The runbook's name, shown when it runs. Required. |
| `description` | What it's for, shown by [`paulrun library`](cli.md#paulrun-library). |
| `output_path` | Where to keep a [transcript](#transcript) of each run. |
| `python` | The command that runs [Python blocks](#python-blocks). |
| `inputs` | Values to ask for. See [Inputs](#inputs). |

Any other key is a `check` warning, so a typo like `ouput_path` gets noticed.

## Inputs

Values a runbook needs each time it runs, such as the version being released.

| Key | What it does |
|---|---|
| `name` | Required, in UPPER_SNAKE_CASE, e.g. `VERSION`. |
| `description` | Required. Shown when paulrun asks for it. |
| `pattern` | A regular expression the whole value must match, e.g. `'^\d+\.\d+\.\d+$'`. |
| `secret` | `true` for passwords and tokens. See [Secrets](#secrets). |
| `default` | Used if you press enter. See [Defaults](#defaults). |
| `choices` | The only values accepted. See [Choices](#choices). |

paulrun collects every input before the first step:

1. If an environment variable with the input's name is set, it's used: `VERSION=1.2.0 paulrun RELEASING.md` doesn't ask. An empty variable counts as not set.
2. Otherwise paulrun asks for it.

A typed answer that doesn't fit the input's `pattern` or `choices` is asked for again. A value from the environment that doesn't fit stops paulrun before anything runs.

### Using inputs

Every input is an environment variable in every `run` block: `$VERSION` in shell, `os.environ["VERSION"]` in Python.

An input that isn't secret can also be written as a placeholder, `<VERSION>`, in `run`, `docstring` and `confirm` blocks and in `output_path`. paulrun fills it in. The rest of the runbook is never changed.

A placeholder that isn't a declared input is a `check` error, and an input nothing uses, as `<VERSION>` or `$VERSION`, is a warning.

!!! warning "Placeholders are filled in as plain text"
    If someone enters `1.2.0; rm -rf ~` for `<VERSION>`, that's what the block runs. Give inputs used in commands a `pattern`.

### Defaults

```yaml
inputs:
  - name: BRANCH
    description: The branch to release from
    default: main
```

```
BRANCH (The branch to release from) [main]:
```

Pressing enter takes `main`. The environment still comes first, and a default must still match the input's `pattern`.

Quote a default YAML would read as something other than text, such as `default: '1.10'`, which would otherwise be the number `1.1`. A secret can't have a default.

### Choices

```yaml
inputs:
  - name: FE_SET
    description: Which frontend set to rebuild
    choices: [comms, billing, all]
    default: comms
```

```
FE_SET (Which frontend set to rebuild) [comms] (comms, billing, all): everything
FE_SET must be one of: comms, billing, all
```

Type the choice itself, not its number. Choices are compared exactly, so `Comms` isn't `comms`. A default must be one of the choices, every choice must match the `pattern` if there is one, and a secret can't have choices.

### Secrets

An input with `secret: true` is never shown or saved:

- Its prompt hides what's typed.
- It's never a placeholder. Read it as `$PUBLISH_TOKEN`; writing `<PUBLISH_TOKEN>` is a `check` error.
- Its value is shown as `****` in block output and the transcript.
- `paulrun --dry` doesn't ask for it.

```sh
uv publish --token "$PUBLISH_TOKEN"
```

!!! note
    paulrun spots a secret by its exact value, one line at a time. A command that encodes it, or splits it across lines, can still reveal it. Pass secrets to commands rather than printing them.

### Input blocks

Some values only exist part way through a run, like the number GitHub gives a pull request you've just opened. An `input` block asks for one when the run reaches it:

````markdown
## Open the pull request

```confirm
Open a pull request for <VERSION> on GitHub.
```

```input
name: PR
description: The number GitHub gave the pull request
pattern: '^\d+$'
```

```sh run
gh pr merge <PR>
```
````

It takes the same keys as a frontmatter input, and works the same from then on.

- Using it before the block, or in `output_path`, is a `check` error.
- `paulrun --dry` doesn't ask for it, and shows `<PR>` as written.

A one-time code is a good use of a secret input block:

````markdown
```input
name: OTP
description: The code from your authenticator app
pattern: '^\d{6}$'
secret: true
```

```sh run
npm publish --otp "$OTP"
```
````

## Steps

Each `##` heading starts a step, named by its text. `###` and smaller headings are just text inside the step.

A block before the first `##` heading is a `check` error.

## Blocks

The first word of a code block's opening line is its language. A second word of `run` makes paulrun run it.

| Block | What paulrun does |
|---|---|
| ```` ```docstring ```` | Shows the text. |
| ```` ```confirm ```` | Shows the text and waits for `y`. Any other answer ends the run. |
| ```` ```input ```` | Asks for an input. See [Input blocks](#input-blocks). |
| ```` ```sh run ```` | Runs it. See [Run blocks](#run-blocks). |
| Anything else, e.g. ```` ```sh ```` | Nothing. It's documentation. |

So a plain ```` ```sh ```` block shows a command without paulrun running it.

````markdown
```docstring
Releasing <VERSION>. This takes a few minutes.
```

```confirm
Create a GitHub release from tag <VERSION>, then come back here.
```
````

### Run blocks

paulrun shows each block's output as it's printed. Exit code `0` carries on; anything else stops the run.

Every block runs with paulrun's environment and every input, plus:

- `PAULRUN_RUNBOOK_DIR`, the folder the runbook is in
- `PYTHONUNBUFFERED=1`, so Python output isn't held back
- `PAGER=cat` and `GIT_PAGER=cat`, so nothing waits in a pager

Run `paulrun backends` to see which languages you can use, or add your own with [backends](backends.md).

#### Where blocks run

Blocks run in the folder you run paulrun from, not the runbook's folder. So one runbook can work on whichever project you're in:

```sh
cd ~/Projects/website
paulrun ~/runbooks/update-deps.md
```

Use `$PAULRUN_RUNBOOK_DIR` for files kept next to the runbook:

```sh
cp "$PAULRUN_RUNBOOK_DIR/templates/pull-request.md" .github/
```

Each block is its own process, so a `cd` or `export` is gone by the next block. Keep commands that need them together.

#### Shell blocks

`sh`, `bash` or `shell`. Each block is one `bash` script that stops at the first failing command, as if it began with `set -eo pipefail`. `check` finds syntax errors, and [shellcheck](install.md#optional-shellcheck) warnings if it's installed.

#### Python blocks

`python` or `py`. Each block is its own script, run with the Python paulrun runs on, so only the standard library is available. To use another interpreter or your project's dependencies, set `python`:

```yaml
python: uv run python
```

`check` compiles each block with paulrun's own Python, so syntax only a newer Python understands isn't caught.

#### Blocks that ask questions

A block can still ask on the terminal, the way `git` and `ssh` ask for a password. But output is shown a line at a time, so a question with no newline after it isn't shown until you answer. Use [inputs](#inputs) for values instead.

## Transcript

Set `output_path`, and each run is added to the end of that file, so a failed attempt and the rerun that fixed it are both kept:

```yaml
output_path: logs/release-<VERSION>.md
```

A relative path is relative to the folder you run paulrun from. Missing folders are created, and `--dry` runs aren't recorded.

```
--- paulrun RELEASING.md @ 2026-10-12T15:11:27+01:00
--- inputs: VERSION=1.2.0 PUBLISH_TOKEN=****

=== Run the tests ===
    make test
<everything make test printed>
exit 0 (4.2s)

=== Publish on GitHub ===
confirm: Create a GitHub release from tag 1.2.0. -> yes

=== Publish to PyPI ===
input: OTP=****
    uv publish --token "$PUBLISH_TOKEN"
skipped (--step)

--- finished: ok (3m12s)
```

The last line says how the run ended:

| Last line | When |
|---|---|
| `--- finished: ok (3m12s)` | Every step ran. |
| `--- finished: failed at "<step>" (exit N)` | A block exited with N. |
| `--- finished: aborted at "<step>"` | A `confirm` wasn't answered `y`, or you quit with [`--step`](cli.md#-step). |
| `--- finished: interrupted at "<step>"` | You pressed Ctrl-C. |

## Known limits

- **bash on macOS** is version 3.2, which can't spot an unclosed heredoc (`cat <<EOF` with no `EOF`).
- **Windows** isn't supported.
