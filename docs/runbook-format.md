# 📜 Runbook format

A runbook is a markdown file. Frontmatter at the top sets it up, each `##` heading is a step, and fenced code blocks marked for paulrun are printed, paused on, or run. Everything else is documentation.

Run `paulrun check` on a runbook at any time to find out what's wrong with it.

## Frontmatter

YAML between `---` lines at the very top of the file:

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

| Key | Required | What it does |
|---|---|---|
| `title` | yes | The runbook's name, shown when it runs. |
| `description` | no | What the runbook is for. For people reading it; paulrun doesn't show it. |
| `output_path` | no | Where to keep a [transcript](#transcript) of each run. |
| `python` | no | The command that runs [Python blocks](#python-blocks). |
| `inputs` | no | Values paulrun asks for before it starts. See [Inputs](#inputs). |

Every value must be text, except `inputs`, which is a list. Any other key is reported by `check` as a warning, so a typo like `ouput_path` doesn't go unnoticed, but it doesn't stop the runbook.

## Inputs

Inputs are values a runbook needs each time it runs, such as the version being released.

| Key | Required | What it does |
|---|---|---|
| `name` | yes | The input's name, in UPPER_SNAKE_CASE, e.g. `VERSION` or `PUBLISH_TOKEN`. |
| `description` | yes | What to enter. Shown when paulrun asks for it. |
| `pattern` | no | A regular expression the whole value must match, e.g. `'^\d+\.\d+\.\d+$'`. |
| `secret` | no | `true` for passwords and tokens. See [Secrets](#secrets). |
| `default` | no | The value to use if you press enter at the prompt, e.g. `main`. See [Defaults](#defaults). |
| `choices` | no | The only values accepted, e.g. `[staging, prod]`. See [Choices](#choices). |

Each name can only be declared once, in the frontmatter or an [input block](#input-blocks). Other keys on an input are `check` warnings.

### How inputs are collected

Frontmatter inputs are all collected before the first step runs, in the order they're declared. [Input blocks](#input-blocks) are collected the same way, but later, when the run reaches them.

1. If an environment variable with the input's name is set, paulrun uses it without asking. `VERSION=1.2.0 paulrun RELEASING.md` releases 1.2.0 with no prompt. An empty variable counts as not set.
2. Otherwise paulrun asks for it, showing its name and description, its default and its choices. Pressing enter takes the default.

If the input has `choices`, the value must be one of them, and if it has a `pattern`, the value must match all of it. A typed answer that isn't accepted is refused and asked for again. A value from the environment that isn't accepted stops paulrun with an error, before anything runs.

### Defaults

Give an input a `default` for the answer you usually give, so pressing enter is enough:

```yaml
inputs:
  - name: BRANCH
    description: The branch to release from
    default: main
```

```
BRANCH (The branch to release from) [main]:
```

The environment still comes first, so `BRANCH=release paulrun RELEASING.md` uses `release` without asking. A default is still checked against the input's `pattern`, like a typed answer.

`check` reports a default that can't work:

- **A default that isn't text.** YAML reads some unquoted values as something else, e.g. `1.10` as the number `1.1` and `yes` as true. Put them in quotes: `default: '1.10'`.
- **A default that doesn't match the input's `pattern`**, since it could never be accepted.
- **A default on a secret**, since the secret would be written in the runbook for anyone to read. paulrun never uses one.

### Choices

Give an input `choices` when only a few values make sense. paulrun lists them at the prompt, and won't take anything else:

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

Type the choice itself, e.g. `billing`, not its number. Choices are compared exactly, so `Comms` isn't `comms`. A value from the environment has to be one of the choices too.

`check` reports choices that can't work:

- **Choices that aren't a list of text**, e.g. `choices: comms` rather than `choices: [comms]`, or an empty list.
- **A choice that doesn't match the input's `pattern`**, since it could never be accepted. You can use both, and a value has to pass both.
- **A default that isn't one of the choices.**
- **Choices on a secret**, since they'd list the secret's possible values in the runbook.

### Using inputs

Every input is set as an environment variable in every `run` block, so a shell block can read `$VERSION` and a Python block `os.environ["VERSION"]`.

An input that isn't secret can also be written as a placeholder, `<VERSION>`, and paulrun replaces it with the value. Placeholders are replaced in:

- `run` blocks, before they run
- `docstring` and `confirm` blocks, before they're shown
- `output_path`

Placeholders are never replaced in the rest of the runbook, so headings and prose are shown exactly as written. A placeholder is `<`, a capital letter, then capital letters, digits or underscores, then `>`. Anything else in angle brackets, such as `<html>`, is left alone.

Using a placeholder that isn't a declared input is a `check` error, as is declaring an input that nothing uses (a warning). Using an input as `$VERSION` in a `run` block counts as using it.

!!! warning "Placeholders are replaced as plain text"
    A value is put into a block exactly as entered. If someone enters `1.2.0; rm -rf ~` for `<VERSION>`, that's what the block runs. Give inputs that end up in commands a `pattern`, so only the values you expect get through.

### Secrets

An input with `secret: true` is for something that mustn't be shown or saved, like an API token:

- Its prompt hides what's typed.
- It's never replaced as a placeholder. Read it from the environment instead, as `$PUBLISH_TOKEN`. Writing `<PUBLISH_TOKEN>` is a `check` error.
- Its value is replaced with `****` everywhere paulrun shows or records it: block output, the transcript, and anywhere it appears in the runbook itself.
- `paulrun --dry` doesn't ask for it at all.

```sh
uv publish --token "$PUBLISH_TOKEN"
```

!!! note "What masking can't catch"
    paulrun hides a secret by spotting its exact value, one line at a time. A command that changes the value before printing it, for example by encoding it, or splits it across two lines, can still reveal it. Pass secrets to commands, rather than printing them.

### Input blocks

Some values don't exist until part way through a run: the number GitHub gives a pull request you've just opened, or a one-time code from an authenticator app that expires in seconds. An `input` block asks for one when the run reaches it, rather than before the first step:

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

An `input` block takes the same keys as a [frontmatter input](#inputs), written as YAML. It's collected the same way, from the environment if it's set or by asking, with its `pattern` checked. From then on it's like any other input: set in the environment of every later `run` block, filled in as a placeholder in later blocks if it isn't secret, and shown as `****` if it is.

It pairs well with `confirm`: do this by hand, then tell paulrun what you got.

Since its value doesn't exist until the run reaches it:

- Using it before the block, as `<PR>` or `$PR`, is a `check` error, and so is using it in `output_path`.
- `paulrun --dry` doesn't ask for it. It shows where the run would stop to ask, and later blocks show `<PR>` as written.
- [`paulrun inputs`](cli.md#paulrun-inputs) lists it with the step that asks for it.

The text inside an `input` block is only read as YAML, so a placeholder in its description is just text.

An OTP is a good example of an input block that should be secret:

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

Each `##` heading starts a step, and its text is the step's name. A step holds every block until the next `##` heading. `###` and smaller headings are just text inside the current step.

A `run`, `docstring`, `confirm` or `input` block before the first `##` heading doesn't belong to a step. That's a `check` error, so it can't be skipped without anyone noticing.

## Blocks

A fenced code block's first line decides what paulrun does with it. The first word is the language, and a second word of `run` makes it a block paulrun runs.

| Fence | What paulrun does |
|---|---|
| ```` ```docstring ```` | Shows the text as it reaches it. |
| ```` ```confirm ```` | Shows the text, then waits for you to answer `y`. Any other answer ends the run. |
| ```` ```input ```` | Asks for an input when the run reaches it. See [Input blocks](#input-blocks). |
| ```` ```sh run ```` | Runs the block. See [Run blocks](#run-blocks). |
| Any other fence, e.g. ```` ```sh ```` or ```` ```python ```` | Nothing. It's documentation. |

A plain ```` ```sh ```` fence is never run, so you can show a command without paulrun running it.

### docstring

Notes to show while the runbook runs, such as what's about to happen:

````markdown
```docstring
Releasing <VERSION>. This takes a few minutes.
```
````

### confirm

A step only a person can do, like clicking a button on a website. paulrun shows the text and waits:

````markdown
```confirm
Create a GitHub release from tag <VERSION>, then come back here.
```
````

Answer `y` to carry on. Any other answer, including just pressing enter, ends the run as aborted, and nothing after it runs.

### Run blocks

A block marked `run` is run by the backend for its language. Each block's output is shown as it's printed, and its exit code decides what happens next: `0` carries on, and anything else stops the run there.

Every block runs:

- in the folder you run paulrun from (see [Where blocks run](#where-blocks-run))
- with paulrun's environment, plus every input
- with `PAULRUN_RUNBOOK_DIR` set to the folder the runbook is in
- with `PYTHONUNBUFFERED=1`, so Python output isn't held back, and `PAGER=cat` and `GIT_PAGER=cat`, so nothing waits in a pager

Run `paulrun backends` to see which languages you can use. Other languages can be added with [backends](backends.md).

#### Where blocks run

Blocks run in the folder you run paulrun from, not the folder the runbook is in. So one runbook can work on whichever project you're in:

```sh
cd ~/Projects/website
paulrun ~/runbooks/update-deps.md    # updates the website's dependencies

cd ~/Projects/api
paulrun ~/runbooks/update-deps.md    # updates the api's
```

A runbook that lives in its project, like a `RELEASING.md` at the root, works the same as long as you run it from there.

A runbook that needs files kept next to it can find them through `PAULRUN_RUNBOOK_DIR`, the folder the runbook is in, as an absolute path:

````markdown
```sh run
cp "$PAULRUN_RUNBOOK_DIR/templates/pull-request.md" .github/
```
````

`PAULRUN_RUNBOOK_DIR` is an environment variable, not an input, so use it as `$PAULRUN_RUNBOOK_DIR`. `<PAULRUN_RUNBOOK_DIR>` is a `check` error, like any undeclared placeholder.

Each block is its own process, so a `cd` or `export` in one block is gone by the next. Put commands that need them in the same block.

#### Shell blocks

Languages: `sh`, `bash`, `shell`.

Each block runs as one `bash` script, so a variable set on one line is still set on the next. It stops at the first command that fails, including one early in a pipe, as if it began with `set -eo pipefail`.

`check` finds syntax errors with `bash -n`, and also uses [shellcheck](install.md#optional-shellcheck) for warnings if it's installed.

#### Python blocks

Languages: `python`, `py`.

Each block runs as its own script, so nothing is shared between blocks except the environment. By default it runs with the Python that paulrun runs on, so only the standard library is available. To use another interpreter, or your project's dependencies, set `python` in the frontmatter:

```yaml
python: uv run python
```

`python` is any command; the block's script is added to the end of it. `check` reports an error if its first word isn't installed.

`check` finds syntax errors by compiling each block with paulrun's own Python, so syntax only a newer Python understands isn't caught.

#### Blocks that ask for input

Blocks should run without anyone answering questions. A block can still ask on the terminal when it has to, the way `git`, `ssh` and `gpg` ask for a password, and that works normally. But anything it prints is shown line by line, so a question without a newline at the end isn't shown until you've answered it.

Values the runbook needs every time are better as [inputs](#inputs), and passwords and tokens as [secrets](#secrets).

## Transcript

Set `output_path`, and paulrun records each run in a plain text file:

```yaml
output_path: logs/release-<VERSION>.md
```

A relative path is relative to the folder you run paulrun from, like the blocks (see [Where blocks run](#where-blocks-run)), so the transcript is kept with the project the run worked on. An absolute path is used as it is. The path can use placeholders, and missing folders are created. Each run is added to the end of the file, so a failed attempt and the rerun that fixed it are both kept. A run that's never started, or a `--dry` run, isn't recorded.

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

Each run starts with a header and the inputs, with secrets as `****`. Each step has its name, then each block's code, indented four spaces, followed by what it printed and its exit code and time. A `confirm` records its first line and the answer, an `input` block records its value where it was given (`****` for a secret), and a block skipped with [`--step`](cli.md#-step) is marked as skipped. `docstring` blocks aren't recorded.

The last line says how the run ended:

| Last line | When |
|---|---|
| `--- finished: ok (3m12s)` | Every step ran. |
| `--- finished: failed at "<step>" (exit N)` | A block in that step exited with N. |
| `--- finished: aborted at "<step>"` | A `confirm` wasn't answered `y`, or you quit with `--step`. |
| `--- finished: interrupted at "<step>"` | You pressed Ctrl-C. A block that was running gets its exit line first. |

## Known limits

- **bash on macOS** is version 3.2, and `check` can't find an unclosed heredoc (`cat <<EOF` with no `EOF`) with it. Newer versions of bash can.
- **Windows** isn't supported.
