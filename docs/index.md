# 🏃‍♂️‍➡️📕 paulrun

## What is paulrun?

paulrun runs hand-written markdown runbooks.

A runbook is a normal markdown file that a person can read and follow without paulrun. Mark a code block `run`, and paulrun runs it for you. Everything else stays documentation.

<div style="text-align: center; padding-top:10px;">
<p>
    <a href="https://pypi.org/project/paulrun">
    <img alt="Package version" src="https://img.shields.io/pypi/v/paulrun?color=%2334D058&label=latest%20version">
    </a>
    <img alt="Python versions" src="https://img.shields.io/badge/python-3.12+-blue">
    <img alt="PyPI - License" src="https://img.shields.io/pypi/l/paulrun">
</p>
</div>

## Example runbook

````markdown
---
title: Release my-package
output_path: logs/release-<VERSION>.md
inputs:
  - name: VERSION
    description: The version to release, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
---

# Releasing my-package

## Run the tests

```sh run
make test
```

## Tag the release

```sh run
git tag <VERSION>
git push origin <VERSION>
```

## Publish on GitHub

```confirm
Create a GitHub release from tag <VERSION>.
```
````

Check it, then run it:

```sh
paulrun check RELEASING.md
paulrun go RELEASING.md
```

paulrun asks for the version, shows you the plan, and runs each step in order, streaming every command's output as it goes. It stops at the first command that fails, and waits for you at the GitHub step, since that one is done by hand:

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
    git push origin 1.2.0
...
exit 0 (1.3s)

=== Publish on GitHub ===
Create a GitHub release from tag 1.2.0.
Continue? [y/N] y

finished: ok (12.8s)
transcript: logs/release-1.2.0.md
```

Every run is also recorded in `logs/release-1.2.0.md`, so you can see afterwards exactly what ran and what it printed.

## Why use paulrun?

Release steps get forgotten. Writing them down helps; making the written-down version run itself fixes it.

- **It's just markdown** - A runbook reads like documentation, renders on GitHub, and works fine without paulrun.
- **Check before you run** - `paulrun check` catches undeclared placeholders, broken frontmatter and shell or Python syntax errors before anything runs.
- **See what would happen** - `paulrun go --dry` shows every command with its inputs filled in, and runs nothing.
- **Inputs and secrets** - Ask for values once, check them against a pattern, and keep secrets out of the screen and the log.
- **Manual steps too** - `confirm` blocks pause for the things only a person can do.
- **A record of every run** - An optional transcript keeps every command, its output and how the run finished.
- **More than shell** - Shell and Python blocks are built in, and other languages can be added as backends.

## Next steps

- [Install paulrun](install.md)
- [The runbook format](runbook-format.md): everything a runbook can contain
- [The command line](cli.md): every command, flag and exit code
- [Backends](backends.md): the languages paulrun runs, and adding your own
