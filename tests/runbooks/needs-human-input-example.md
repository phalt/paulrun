---
title: Needs human input example
description: Run without asking anything, and stop where a person has to act.
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
---

# Needs human input example

With `--no-input`, rundot never asks anything. When the run reaches a confirm,
or an input block with no value, it stops with exit code 3 and says what a
person has to do. Run the same command again once it's done.

```sh
VERSION=1.2.0 uv run rundot tests/runbooks/needs-human-input-example.md --no-input
VERSION=1.2.0 uv run rundot tests/runbooks/needs-human-input-example.md --no-input
PR=42 VERSION=1.2.0 uv run rundot tests/runbooks/needs-human-input-example.md --no-input
```

The first run stops at the confirm. The second carries on after it and stops
at the input block. The third, with `PR` set, finishes.

## Build

```sh run
echo "Building <VERSION>"
```

## Release notes

```confirm
Publish the GitHub release notes for v<VERSION>.
Then tell the team.
```

## Announce

```input
name: PR
description: The number GitHub gave the pull request
pattern: '^\d+$'
```

```sh run
echo "Announcing <VERSION> in PR <PR>"
```
