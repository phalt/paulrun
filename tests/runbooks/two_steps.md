---
title: Two steps
---

# Two steps

A shell-only runbook for watching `rundot` stream output. Its blocks run
in the directory you start rundot from, wherever the runbook itself is:

```sh
cd /tmp
uv run --project ~/Projects/rundot rundot ~/Projects/rundot/tests/runbooks/two_steps.md
```

## Count slowly

```sh run
for i in 1 2 3; do echo "$i"; sleep 0.2; done
```

## Say where

`pwd` is where rundot was started. `RUNDOT_RUNBOOK_DIR` is where this file
is, for a runbook that needs files kept next to it.

```sh run
pwd -P
echo "runbook: $RUNDOT_RUNBOOK_DIR"
```
