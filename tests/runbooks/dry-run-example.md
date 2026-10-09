---
title: Dry run example
description: See what a release would do, without doing any of it.
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
  - name: PUBLISH_TOKEN
    description: Token for the package index
    secret: true
---

# Dry run example

`--dry` goes through the runbook like a real run and prints every block with
inputs filled in, but runs nothing:

```sh
VERSION=1.2.0 uv run paulrun go --dry tests/runbooks/dry-run-example.md
```

There's no start prompt and `confirm` blocks don't wait. Plain inputs are still
asked for, so the blocks can be shown filled in. Secrets aren't needed, so
they're never asked for and are shown as `****`.

Every block here would write a file next to this runbook. After a dry run,
none of them exist.

## Build

```sh run
echo "<VERSION>" > built-<VERSION>.txt
```

## Publish

```confirm
Check built-<VERSION>.txt before publishing.
```

```sh run
echo "published with $PUBLISH_TOKEN" > published-<VERSION>.txt
```
