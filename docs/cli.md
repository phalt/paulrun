# 📟 Command line

```sh
paulrun RUNBOOK [--dry] [--step]      # run a runbook
paulrun run RUNBOOK [--dry] [--step]  # the same, in full
paulrun check RUNBOOK                 # find problems without running anything
paulrun inputs RUNBOOK                # list the inputs a runbook needs
paulrun library                       # list the books in your runbook library
paulrun backends                      # list the languages paulrun can run
paulrun --version
```

`paulrun` on its own shows this list, with a line about each command.

## Naming a runbook

`RUNBOOK` is a path to a runbook file, or the name of a book in your runbook library.

```sh
paulrun RELEASING.md        # the file RELEASING.md, here
paulrun rebuild-frontend    # the book rebuild-frontend.md, in your library
```

Your runbook library is a folder of runbooks you keep for yourself, rather than in a project. It's `~/runbooks`, unless you set `PAULRUN_LIBRARY` to somewhere else:

```sh
export PAULRUN_LIBRARY=~/work-runbooks
```

Run [`paulrun library`](#paulrun-library) to see which books are in it.

paulrun works out which runbook you mean like this:

1. If `RUNBOOK` is a file that exists, that's the runbook. A runbook in your project is never hidden by a book with the same name.
2. Otherwise, if it has no `/` in it, it's a book's name, and paulrun uses `<name>.md` from your library. `rebuild-frontend` and `rebuild-frontend.md` are the same book.
3. Otherwise there's no such runbook, which is a usage error. paulrun names the places it looked:

```
Error: Invalid value for 'RUNBOOK': no runbook 'rebuild-frontend': no such file here, and no rebuild-frontend.md in the library at /home/you/runbooks
```

Wherever the runbook comes from, its blocks run in the folder you run paulrun from. See [Where blocks run](runbook-format.md#where-blocks-run).

## paulrun run

Runs a runbook, step by step. `RUNBOOK` is a file or a book in your library; see [Naming a runbook](#naming-a-runbook).

```sh
paulrun RELEASING.md
```

You don't need to type `run`: anything after `paulrun` that isn't one of its commands is a runbook to run. `paulrun run RELEASING.md` does exactly the same, and is how you run a book whose name is also a command, e.g. `paulrun run check` for a book called `check.md`, since `paulrun check` is always the `check` command. Options can go before or after the runbook, so `paulrun RELEASING.md --dry` and `paulrun --dry RELEASING.md` are the same.

1. **Checks the runbook** first, exactly as [`paulrun check`](#paulrun-check) does. Any error stops it here, before anything runs. Warnings are shown, then it carries on.
2. **Collects the inputs**, from the environment or by asking. See [How inputs are collected](runbook-format.md#how-inputs-are-collected).
3. **Shows the plan** (the title, the folder blocks will run in, the inputs, each step, and how many blocks will run) and asks `Start? [y/N]`.
4. **Goes through each step in order**, showing its name, then each block: notes are shown, `confirm` blocks wait for `y`, [`input` blocks](runbook-format.md#input-blocks) ask for their value, and `run` blocks run with their output streamed as it's printed.

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

The run stops at the first block that fails, and later steps don't run:

```
=== Build ===
    echo "Building"
    exit 2
Building
exit 2 (0.0s)

finished: failed at "Build" (exit 2)
```

Only `y` answers `Start?` and `Continue?` with a yes. Anything else, including just pressing enter, ends the run as aborted.

If the runbook has an [`output_path`](runbook-format.md#transcript), the run is recorded there, and the last line says where.

### Picking a book

With no runbook, `paulrun run` lists the books in your [runbook library](#naming-a-runbook) and asks which one to run:

```
$ paulrun run
  1. rebuild-frontend     Rebuild the frontend
  2. update-project-deps  Update a project's dependencies
Run which? 1
```

Answer with a book's number, and it runs exactly as if you'd typed its name. `--dry` and `--step` work too: `paulrun run --dry` picks a book, then shows what it would do. Any other answer gets the question again. Press enter without answering, or Ctrl-C, to stop without running anything.

`paulrun` on its own shows help rather than the picker, so you need the `run`.

### --dry

Shows what the runbook would do, without doing any of it.

```sh
paulrun --dry RELEASING.md
```

Every block is shown with its inputs filled in, but nothing runs. The plan still shows the folder blocks would run in, so you can check it before a real run. There's no `Start?` question, `confirm` blocks don't wait, and no transcript is written. Frontmatter inputs are still collected, so the blocks can be filled in, but secrets aren't needed, so they aren't asked for and show as `****`. [`input` blocks](runbook-format.md#input-blocks) aren't asked for either, since their values may not exist yet: each shows where the run would stop to ask, and later blocks show its placeholder as written.

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

Asks about every `run` block before running it.

```sh
paulrun --step RELEASING.md
```

After each block's code is shown, paulrun asks `Run this block? [y]es / [s]kip / [q]uit`:

- `y` runs the block.
- `s` skips it, and the run carries on with the next block.
- `q` quits, and the run ends as aborted.

Any other answer gets the question again. Skipped blocks are marked as skipped in the transcript. `--step` only asks about `run` blocks; `input` blocks are always asked. With `--dry`, `--step` does nothing, since nothing runs anyway.

```
=== Build ===
    echo "Building"
Run this block? [y]es / [s]kip / [q]uit y
Building
exit 0 (0.0s)

=== Publish ===
    echo "Publishing"
Run this block? [y]es / [s]kip / [q]uit s
skipped (--step)

finished: ok (0.0s)
```

### Pressing Ctrl-C

Ctrl-C stops the run, cleanly:

- If a block is running, it gets the Ctrl-C too, and paulrun waits for it to stop, still showing anything it prints. Its exit code is recorded.
- If a block ignores Ctrl-C, press it again. paulrun stops the block and everything it started.
- Later steps don't run, and the run ends as `finished: interrupted at "<step>"`, in the transcript too.

## paulrun check

Finds problems in a runbook without running anything. Like `run`, it takes a file or a book's name.

```sh
paulrun check RELEASING.md
```

```
RELEASING.md: ok
```

Each problem is shown with the line it's on, so your editor can jump to it, then a count:

```
broken.md:6: error: input VERSION is declared twice (first on line 4)
broken.md:8: warning: input BRANCH is never used
broken.md:12: error: run blocks must be inside a step (a ## heading)
broken.md:19: error: <TAG> isn't a declared input
broken.md:21: error: syntax error near unexpected token `fi'

4 errors, 1 warning
```

**Errors** are problems that would make the runbook go wrong:

- a missing `title`, or a frontmatter value of the wrong type
- an input without a `name` or `description`, a name that isn't UPPER_SNAKE_CASE, a name declared twice, or a `pattern` that isn't a valid regular expression
- an `input` block that isn't valid YAML, or isn't a mapping
- a placeholder that isn't a declared input, or a secret used as a placeholder
- an `input` block's value used before the block, or in `output_path`
- a `run`, `docstring`, `confirm` or `input` block before the first `##` heading
- a `run` block in a language no backend runs
- a `python` command that isn't installed
- a syntax error in a shell or Python block

**Warnings** are worth a look, but don't stop the runbook:

- a frontmatter or input key paulrun doesn't know, which is often a typo
- an input nothing uses
- a Python `SyntaxWarning`, and [shellcheck](install.md#optional-shellcheck) findings if it's installed

`paulrun run` runs the same checks before it starts.

## paulrun inputs

Lists the inputs a runbook needs, so you know what to have ready, or what to set in the environment. Like `run`, it takes a file or a book's name.

```sh
paulrun inputs PUBLISHING.md
```

```
VERSION  The version being released, e.g. 1.2.0
         pattern: ^\d+\.\d+\.\d+$
BRANCH   The branch to release from
         default: main
ENV      Where to deploy
         choices: staging, prod
PR       The number GitHub gave the pull request
         pattern: ^\d+$
         asked in "Open the pull request"
OTP      The code from your authenticator app
         pattern: ^\d{6}$
         secret
         asked in "Publish"
```

Frontmatter inputs come first. Inputs from [`input` blocks](runbook-format.md#input-blocks) come after, each with the step that asks for it.

If the rest of the runbook is broken, the frontmatter inputs are still listed; input blocks need the rest of the runbook to be readable. Inputs that are missing a name or description aren't listed; `paulrun check` reports those.

## paulrun library

Lists the books in your [runbook library](#naming-a-runbook), so you can find the one you need.

```sh
paulrun library
```

```
library: /home/you/runbooks
rebuild-frontend     Rebuild the frontend
                     Clean install the frontend's dependencies, then rebuild it.
update-project-deps  Update a project's dependencies
```

Each book is listed by the name you run it with, then its `title`, with its `description` underneath. Every `.md` file directly in the library is a book. Other files and folders in it are left out, so a `logs/` folder there is a fine place for transcripts.

Only each book's frontmatter is read. A book whose frontmatter can't be read is still listed, with why, so you can fix it:

```
deploy    can't read it: frontmatter has no closing ---
```

If the library is empty, or doesn't exist yet, paulrun says where it looked.

## paulrun backends

Lists the languages paulrun can run, and the package each one comes from.

```sh
paulrun backends
```

```
python  python, py       paulrun.backends.python:PythonBackend (paulrun 0.1.0)
shell   sh, bash, shell  paulrun.backends.shell:ShellBackend (paulrun 0.1.0)
```

Backends installed from other packages are listed here too.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The run finished, or `check` found no errors. A `--dry` run, and a run where every block was skipped, exit 0 too. |
| `1` | A block failed, the run was aborted or interrupted, `check` found errors, or the runbook couldn't be read. |
| `2` | The command was used wrongly, e.g. a runbook that isn't a file or a book in your library. |
