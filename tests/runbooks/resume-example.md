---
title: Resume example
description: Pick a run up at the step it stopped in.
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
  - name: PUBLISH_TOKEN
    description: Token for the package index
    secret: true
---

# Resume example

The Publish step fails until there's a file called `fixed` where rundot runs.

```sh
VERSION=1.2.0 uv run rundot tests/runbooks/resume-example.md
touch fixed
VERSION=1.2.0 uv run rundot tests/runbooks/resume-example.md
```

The second run asks whether to resume. Answer `r`, and only Publish and
Announce run. `VERSION` is saved from the first run, but `PUBLISH_TOKEN` is a
secret, so it's asked for again.

## Build

```sh run
echo "Building <VERSION>"
```

## Test

```sh run
echo "Testing <VERSION>"
```

## Publish

```sh run
test -f fixed || { echo "not fixed yet" >&2; exit 1; }
echo "Publishing <VERSION> with $PUBLISH_TOKEN"
```

## Announce

```sh run
echo "Announced <VERSION>"
```
