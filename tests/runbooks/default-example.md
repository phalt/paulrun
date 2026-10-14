---
title: Default example
description: Offer a default for an input, so pressing enter is enough.
inputs:
  - name: BRANCH
    description: The branch to release from
    default: main
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
---

# Default example

An input with a `default` shows it at the prompt, and pressing enter takes it:

```sh
VERSION=1.2.0 uv run paulrun tests/runbooks/default-example.md
```

```
BRANCH (The branch to release from) [main]:
```

The environment still comes first, so `BRANCH=release` skips the prompt and
uses `release`. A default has to be quoted if YAML would read it as something
other than text, e.g. `default: '1.10'`, and it has to match the input's
`pattern` if there is one. A secret can't have a default, because its value
would be written here for anyone to read.

## Release

```sh run
echo "Releasing <VERSION> from <BRANCH>"
```
