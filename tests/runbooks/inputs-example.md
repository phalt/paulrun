---
title: Inputs example
description: Ask for a version and a token, then use them in run blocks.
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
  - name: PUBLISH_TOKEN
    description: Token for the package index
    secret: true
---

# Inputs example

paulrun asks for each input before the first step runs, unless it's already set
in the environment:

```sh
uv run paulrun go tests/runbooks/inputs-example.md
VERSION=1.2.0 uv run paulrun go tests/runbooks/inputs-example.md
```

`VERSION` has to match its pattern, so an answer like `latest` is refused and
asked for again. `PUBLISH_TOKEN` is secret, so it's hidden as you type it.

## Tag the release

`<VERSION>` in a `run` block is replaced with its value before the block runs:

```sh run
echo "Tagging <VERSION>"
```

## Publish

Every input is also an environment variable. That's the only way to use a
secret: it's never substituted, and paulrun prints `****` wherever a block
prints its value.

```sh run
echo "Publishing <VERSION> with $PUBLISH_TOKEN"
```
