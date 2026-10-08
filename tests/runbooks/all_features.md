---
title: Release example
description: A runbook that uses every part of the format.
output_path: logs/release-<VERSION>.md
python: python3
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
  - name: PUBLISH_TOKEN
    description: Token for the package index
    secret: true
---

# Release example

Everything before the first step is documentation. This fence isn't marked
`run`, so paulrun ignores it:

```sh
echo "for reading only"
```

## Check the version

```docstring
Releasing <VERSION>.
```

```sh run
echo "Releasing <VERSION>"
```

### Why a subheading

A `###` heading is prose inside the current step.

## Update the version

Set the version in `pyproject.toml`:

```toml
version = "<VERSION>"
```

```confirm
Set version = "<VERSION>" in pyproject.toml and save it.
```

```python run
print("Version <VERSION> set")
```

## Build and publish

1. Build the package:

   ```bash run
   echo "Building <VERSION>"
   ```

2. Publish it. The token comes from the environment and is never substituted:

   ```shell run
   echo "Publishing with a ${#PUBLISH_TOKEN} character token"
   ```

Plain `python` fences are documentation too:

```python
print("not run")
```
