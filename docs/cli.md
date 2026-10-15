# 📟 Command line

```sh
paulrun RUNBOOK [--dry] [--step | --no-step]      # run a runbook
paulrun run RUNBOOK [--dry] [--step | --no-step]  # the same, in full
paulrun check RUNBOOK                             # find problems without running anything
paulrun inputs RUNBOOK                            # list the inputs a runbook needs
paulrun library                                   # list the books in your runbook library
paulrun backends                                  # list the languages paulrun can run
paulrun --version
```

`paulrun` on its own shows this list.

## Naming a runbook

`RUNBOOK` is a file, or the name of a book in your [runbook library](library.md):

```sh
paulrun RELEASING.md        # the file RELEASING.md, here
paulrun rebuild-frontend    # the book rebuild-frontend.md, in your library
```

1. If `RUNBOOK` is a file that exists, that's the runbook, so a file is never hidden by a book with the same name.
2. Otherwise, if it has no `/`, it's the book `<name>.md` in your library. The `.md` is optional.
3. Otherwise it's a usage error, which names both places paulrun looked:

```
Error: Invalid value for 'RUNBOOK': no runbook 'rebuild-frontend': no such file here, and no rebuild-frontend.md in the library at /home/you/runbooks
```

## paulrun run

Runs a runbook, step by step.

```sh
paulrun RELEASING.md
```

You don't need to type `run`: anything after `paulrun` that isn't a command is a runbook. Options go before or after it, so `paulrun RELEASING.md --dry` is the same as `paulrun --dry RELEASING.md`. Use `paulrun run check` to run a book called `check.md`, since `paulrun check` is the command.

1. **Checks the runbook**, as [`paulrun check`](#paulrun-check) does. Errors stop it here.
2. **Collects the inputs**. See [Inputs](runbook-format.md#inputs).
3. **Shows the plan** and asks `Start? [y/N]`.
4. **Runs each step in order**, streaming each block's output as it's printed.

```
VERSION (The version to release, e.g. 1.2.0): 1.2.0
Release my-package
directory: /home/you/Projects/my-package
inputs: VERSION=1.2.0
  1. Run the tests
  2. Tag the release
  3. Publish on GitHub
2 run blocks
Start? [y/N] y

=== Run the tests ===
    make test
...
exit 0 (4.2s)

=== Tag the release ===
    git tag 1.2.0
...
exit 0 (0.1s)

=== Publish on GitHub ===
Create a GitHub release from tag 1.2.0.
Continue? [y/N] y

finished: ok (12.8s)
transcript: logs/release-1.2.0.md
```

`directory:` is where blocks will run. See [Where blocks run](runbook-format.md#where-blocks-run).

The run stops at the first block that fails:

```
=== Build ===
    echo "Building"
    exit 2
Building
exit 2 (0.0s)

finished: failed at "Build" (exit 2)
```

Only `y` answers `Start?` and `Continue?` with yes. Anything else, including enter, ends the run as aborted.

### Picking a book

With no runbook, `paulrun run` asks which book from your library to run:

```
$ paulrun run
  1. rebuild-frontend     Rebuild the frontend
  2. update-project-deps  Update a project's dependencies
Run which? (q to quit) 1
```

Answer with a number. `--dry` and `--step` work too. Answer `q`, or press enter, to stop without running anything.

### --dry

Shows what the runbook would do, without running anything.

```sh
paulrun --dry RELEASING.md
```

- Every block is shown with its inputs filled in.
- There's no `Start?`, `confirm` blocks don't wait, and no transcript is written.
- Secrets and [input blocks](runbook-format.md#input-blocks) aren't asked for.

```
VERSION (The version to release, e.g. 1.2.0): 1.2.0
Release my-package
directory: /home/you/Projects/my-package
inputs: VERSION=1.2.0
  1. Run the tests
  2. Tag the release
  3. Publish on GitHub
2 run blocks
dry run: nothing will be run

=== Run the tests ===
    make test

=== Tag the release ===
    git tag 1.2.0

=== Publish on GitHub ===
Create a GitHub release from tag 1.2.0.

finished: dry run, nothing was run
```

### --step

Asks before running each `run` block.

```sh
paulrun --step RELEASING.md
```

```
=== Build ===
    echo "Building"
Run this block? [y]es / [s]kip / [q]uit y
Building
exit 0 (0.0s)

=== Publish ===
    echo "Publishing"
Run this block? [y]es / [s]kip / [q]uit s
skipped

finished: ok (0.0s)
```

`y` runs the block, `s` skips it, and `q` ends the run as aborted. With `--dry`, `--step` does nothing, since nothing runs.

A runbook that should always be run this way can set [`step: true`](runbook-format.md#frontmatter) in its frontmatter, so you don't need to remember `--step`. To run one of those straight through, pass `--no-step`.

### Pressing Ctrl-C

- A running block gets the Ctrl-C too, and paulrun waits for it to stop.
- If a block ignores it, press Ctrl-C again to stop the block and everything it started.
- The run ends as `finished: interrupted at "<step>"`.

## paulrun check

Finds problems in a runbook without running anything.

```sh
paulrun check RELEASING.md
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

- a frontmatter or input key paulrun doesn't know, often a typo
- an input nothing uses
- a Python `SyntaxWarning`, and [shellcheck](install.md#optional-shellcheck) findings if it's installed

## paulrun inputs

Lists the inputs a runbook needs, so you know what to have ready.

```sh
paulrun inputs PUBLISHING.md
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

## paulrun library

Lists the books in your [runbook library](library.md), with each one's `title` and `description`.

```
$ paulrun library
library: /home/you/runbooks
rebuild-frontend     Rebuild the frontend
                     Clean install the frontend's dependencies, then rebuild it.
update-project-deps  Update a project's dependencies
```

A book whose frontmatter can't be read is still listed, with why.

## paulrun backends

Lists the languages paulrun can run, and the package each comes from.

```
$ paulrun backends
python  python, py       paulrun.backends.python:PythonBackend (paulrun 0.2.0)
shell   sh, bash, shell  paulrun.backends.shell:ShellBackend (paulrun 0.2.0)
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The run finished, or `check` found no errors. |
| `1` | A block failed, the run was aborted or interrupted, `check` found errors, or the runbook couldn't be read. |
| `2` | The command was used wrongly, e.g. a runbook that doesn't exist. |
