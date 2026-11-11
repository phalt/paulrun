# 🏃‍♂️‍➡️📕 rundot

## What is rundot?

rundot executes the code blocks in your markdown file, turning them into runbooks.

A runbook is just a normal markdown file that a person can read and write, but if you annotate a code block `run`, then rundot can execute the code blocks for you, helping you to automate tedious multi-step tasks.

[![Package version](https://img.shields.io/pypi/v/rundot?color=%2334D058&label=latest%20version)](https://pypi.org/project/rundot)
![Python versions](https://img.shields.io/badge/python-3.12+-blue)
![PyPI - License](https://img.shields.io/pypi/l/rundot)

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

A runbook is just markdown. rundot runs the blocks marked `run`, shows the
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
rundot check hello.md
rundot hello.md
```

![rundot checking and running hello.md](docs/demo.svg)

The command `check` will validate the formatting of your Markdown file to make sure it will work with Rundot. 

When running a runbook, rundot asks for the inputs, shows the plan, and runs each step in order.

You can run through each step one at a time with `--step` and even show the code that will run with each step with `--show-code`.

## Your runbook library

Keep runbooks you use across projects in `~/runbooks`, and run them by name from anywhere:

```
$ rundot library
library: /home/you/runbooks
rebuild-frontend     Rebuild the frontend
update-project-deps  Update a project's dependencies

$ cd ~/Projects/website
$ rundot rebuild-frontend
```

A book runs in the folder you're in, so one book works for every project. See [Your runbook library](https://docs.rundot.dev/library/).

## Why use rundot?

Release steps get forgotten. Writing them down helps; making the written-down version run itself fixes it.

- **It's just markdown** - A runbook reads like documentation, renders on GitHub, and works fine without rundot.
- **Check before you run** - `rundot check` finds broken frontmatter, undeclared placeholders and syntax errors.
- **See what would happen** - `rundot --dry RELEASING.md` shows every command with its inputs filled in, and runs nothing.
- **Inputs and secrets** - Ask for values once, check them against a pattern, and keep secrets off the screen and out of the log.
- **Manual steps too** - `confirm` blocks pause for the things only a person can do.
- **A record of every run** - An optional transcript keeps every command, its output and how it finished.
- **More than shell** - Shell and Python blocks are built in, and other languages can be added as backends.

## Install

rundot is a command-line tool, so install it on its own rather than into a project:

```sh
uv tool install rundot
```

Or with pip:

```sh
pip install rundot
```

rundot needs Python 3.12 or later and `bash`, and runs on **macOS and Linux**. Windows isn't supported. It's for runbooks you run yourself, at a terminal; there's no CI mode.

## Getting started

👉 Read the [full documentation](https://docs.rundot.dev/) for the runbook format, every command, and writing your own backend.

See [`examples/`](https://github.com/phalt/rundot/tree/main/examples) for more runbooks, including a real release, and [`PUBLISHING.md`](https://github.com/phalt/rundot/blob/main/PUBLISHING.md) for the runbook rundot releases itself with.

Want to help? See [CONTRIBUTING.md](https://github.com/phalt/rundot/blob/main/CONTRIBUTING.md).
