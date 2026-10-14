# 🏃‍♂️‍➡️📕 paulrun

## What is paulrun?

paulrun runs hand-written markdown runbooks.

A runbook is a normal markdown file that a person can read and follow without paulrun. Mark a code block `run`, and paulrun runs it for you. Everything else stays documentation.

[![Package version](https://img.shields.io/pypi/v/paulrun?color=%2334D058&label=latest%20version)](https://pypi.org/project/paulrun)
![Python versions](https://img.shields.io/badge/python-3.12+-blue)
![PyPI - License](https://img.shields.io/pypi/l/paulrun)

## Example runbook

Save this as `hello.md`:

````markdown
---
title: Say hello
inputs:
  - name: NAME
    description: Who to say hello to
---

# Say hello

A runbook is just markdown. paulrun runs the blocks marked `run`, shows the
`docstring` ones, and leaves everything else alone, like this paragraph.

## Greet

```docstring
Saying hello to <NAME>.
```

```sh run
echo "Hello, <NAME>!"
```

## Count the letters

```python run
import os

name = os.environ["NAME"]
print(f"{name} has {len(name)} letters")
```
````

Check it, then run it:

```sh
paulrun check hello.md
paulrun hello.md
```

```
hello.md: ok
NAME (Who to say hello to): Paul
Say hello
directory: /home/you/hello
inputs: NAME=Paul
  1. Greet
  2. Count the letters
2 run blocks
Start? [y/N] y

=== Greet ===
Saying hello to Paul.
    echo "Hello, Paul!"
Hello, Paul!
exit 0 (0.0s)

=== Count the letters ===
    import os

    name = os.environ["NAME"]
    print(f"{name} has {len(name)} letters")
Paul has 4 letters
exit 0 (0.1s)

finished: ok (0.1s)
```

`check` finds problems before anything runs. Running it asks for the inputs, shows you the plan, then runs each step in order, streaming every command's output as it goes. It stops at the first command that fails.

## Your runbook library

Keep runbooks you use across projects in `~/runbooks`, your runbook library, and run them by name from anywhere:

```
$ paulrun library
library: /home/you/runbooks
rebuild-frontend     Rebuild the frontend
update-project-deps  Update a project's dependencies

$ cd ~/Projects/website
$ paulrun rebuild-frontend
```

A book runs in the folder you're in, so one book works on whichever project you run it from. `paulrun run` with no name lets you pick one from a list. See [Your runbook library](https://phalt.github.io/paulrun/library/).

## Why use paulrun?

Release steps get forgotten. Writing them down helps; making the written-down version run itself fixes it.

- **It's just markdown** - A runbook reads like documentation, renders on GitHub, and works fine without paulrun.
- **Check before you run** - `paulrun check` catches undeclared placeholders, broken frontmatter and shell or Python syntax errors before anything runs.
- **See what would happen** - `paulrun --dry RELEASING.md` shows every command with its inputs filled in, and runs nothing.
- **Inputs and secrets** - Ask for values once, check them against a pattern, and keep secrets off the screen and out of the log.
- **Manual steps too** - `confirm` blocks pause for the things only a person can do.
- **A record of every run** - An optional transcript keeps every command, its output and how the run finished.
- **A library of your own** - Keep runbooks you use everywhere in `~/runbooks`, and run any of them by name from whichever project you're in.
- **More than shell** - Shell and Python blocks are built in, and other languages can be added as backends.

## Install

paulrun is a command-line tool, so install it on its own rather than into a project:

```sh
uv tool install paulrun
```

Or with pip:

```sh
pip install paulrun
```

paulrun needs Python 3.12 or later and `bash`, and runs on **macOS and Linux**. Windows isn't supported. It's for runbooks you run yourself, at a terminal; there's no CI mode.

## Getting started

👉 Read the [full documentation](https://phalt.github.io/paulrun/) for the runbook format, every command, and writing your own backend.

See [`examples/`](https://github.com/phalt/paulrun/tree/main/examples) for more runbooks, including a real release, and [`PUBLISHING.md`](https://github.com/phalt/paulrun/blob/main/PUBLISHING.md) for the runbook paulrun releases itself with.

Want to help? See [CONTRIBUTING.md](https://github.com/phalt/paulrun/blob/main/CONTRIBUTING.md).
