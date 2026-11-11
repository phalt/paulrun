# 🏃‍♂️‍➡️📕 Rundot

[![Package version](https://img.shields.io/pypi/v/rundot?color=%2334D058&label=latest%20version)](https://pypi.org/project/rundot)
![Python versions](https://img.shields.io/badge/python-3.12+-blue)
![PyPI - License](https://img.shields.io/pypi/l/rundot)

**Markdown that runs.**

Rundot runs the code blocks in a markdown file, one step at a time. Write a release checklist, a deploy or a setup guide once, and run it the same way every time.

![rundot checking and running hello.md](demo.svg)

🌐 [rundot.dev](https://rundot.dev) · 🚀 [Install](install.md) · 🤖 [Prompt for your LLM](https://rundot.dev/prompt.txt)

## What people use it for

- **Release checklists** - Tag, build, publish, announce. In order, every time.
- **Incident runbooks** - The steps you need at 3am, already checked.
- **Dev setup** - One setup guide that works the same on every machine.
- **Onboarding** - Guides new contributors can run, not just read.
- **Deploys** - Ask before anything destructive happens.
- **Database migrations** - Backups and safety checks built into the steps.
- **Agent procedures** - Fixed steps for your LLM to follow.
- **Rare chores** - The job you do twice a year and always forget.

## It's just markdown

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

rundot asks for the inputs, shows the plan, and runs each step in order. A runbook reads like documentation and renders on GitHub, so it's still useful without rundot installed.

## Know it works before it runs

`rundot check` catches broken frontmatter, undeclared placeholders, and shell or Python syntax errors, with line numbers.

`rundot --dry hello.md` prints every command with its inputs filled in, and runs nothing.

Go one step at a time with `--step`, and see each block's code as it runs with `--show-code`.

## Pause for the bits only a person can do

A `confirm` block stops the run until someone answers `y`:

````md
```confirm
Publish the GitHub release notes for v<VERSION>.
```
````

Inputs can be checked against a pattern or a list of choices. Secrets are hidden as you type them and shown as `****` in the output and the transcript.

## Your runbooks, everywhere

Keep runbooks you use across projects in `~/runbooks`, and run them by name from anywhere:

```
$ rundot library
library: /home/you/runbooks
rebuild-frontend     Rebuild the frontend
update-project-deps  Update a project's dependencies

$ cd ~/Projects/website
$ rundot rebuild-frontend
```

A book runs in the folder you're in, so the same one works in every project. See [Your runbook library](library.md).

## Agents improvise. Runbooks don't.

A runbook gives an agent a fixed set of steps to follow instead of working them out each time. Paste [this prompt](https://rundot.dev/prompt.txt) into your chat, or into your `CLAUDE.md` or `AGENTS.md`. It teaches the format and asks the agent to check and dry-run every runbook before running it.

## Also in rundot

- **Transcripts** - Set `output_path` to keep every command, its output and how the run ended.
- **More than shell** - Shell and Python are built in. Other languages can be added as backends.

## Next steps

- [Install rundot](install.md)
- [The runbook format](runbook-format.md): everything a runbook can contain
- [The command line](cli.md): every command, flag and exit code
- [Your runbook library](library.md): runbooks you keep for yourself, and run from anywhere
- [Backends](backends.md): the languages rundot runs, and adding your own
