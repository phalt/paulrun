---
title: Update a project's dependencies
description: Upgrade every dependency in the project you're in, then run its tests.
inputs:
  - name: BRANCH
    description: The branch to make the update on, e.g. update-deps
---

# Update a project's dependencies

A book for any `uv` project. Run it from the project you want to update:

```sh
cd ~/Projects/my-package
paulrun update-project-deps
```

This copy only says what it would do, so it's safe to run anywhere.

## Make a branch

```sh run
echo "git switch -c <BRANCH>"
```

## Upgrade and test

```sh run
echo "uv lock --upgrade in $(basename "$PWD")"
echo "make test"
```
