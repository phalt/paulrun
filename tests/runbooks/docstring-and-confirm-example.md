---
title: Docstring and confirm example
description: Print notes as you go, and pause for steps done by hand.
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
---

# Docstring and confirm example

paulrun prints `docstring` blocks as it reaches them, and stops at each
`confirm` block until you answer `y`. Any other answer ends the run there, and
nothing after it runs.

```sh
VERSION=1.2.0 uv run paulrun go tests/runbooks/docstring-and-confirm-example.md
```

Both kinds of block have plain inputs substituted, like `run` blocks.

## Build

```docstring
Building <VERSION>. This only echoes; nothing is built.
```

```sh run
echo "Built <VERSION>"
```

## Release on GitHub

Creating the release is done by hand, in the browser:

```confirm
Create a GitHub release for tag <VERSION> and publish it.
```

```sh run
echo "Released <VERSION>"
```
