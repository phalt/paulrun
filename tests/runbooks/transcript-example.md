---
title: Transcript example
description: Keep a record of every run in a file.
output_path: logs/release-<VERSION>.md
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
  - name: PUBLISH_TOKEN
    description: Token for the package index
    secret: true
---

# Transcript example

With `output_path` set, `paulrun go` adds a plain record of each run to that
file: every command, what it printed, its exit code, and how the run finished.

```sh
VERSION=1.2.0 uv run paulrun go tests/runbooks/transcript-example.md
```

The path is relative to the directory you run paulrun from, not this runbook,
so the command above writes `logs/release-1.2.0.md` at the top of the
repository. It can use plain inputs, and its directory is created if it
doesn't exist. Each run is added to the end, so a failed attempt and its rerun
are both kept. Secrets are written as `****`, even if a block prints one.
`--dry` writes nothing.

## Build

```sh run
echo "Building <VERSION>"
```

## Release on GitHub

```confirm
Create a GitHub release for tag <VERSION> and publish it.
```

## Publish

```sh run
echo "Publishing <VERSION> with $PUBLISH_TOKEN"
```
