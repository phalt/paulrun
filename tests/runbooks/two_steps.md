---
title: Two steps
---

# Two steps

A shell-only runbook for watching `paulrun go` stream output. Its blocks run
in the directory you start paulrun from, wherever the runbook itself is:

```sh
cd /tmp
uv run --project ~/Projects/paulrun paulrun go ~/Projects/paulrun/tests/runbooks/two_steps.md
```

## Count slowly

```sh run
for i in 1 2 3; do echo "$i"; sleep 0.2; done
```

## Say where

`pwd` is where paulrun was started. `PAULRUN_RUNBOOK_DIR` is where this file
is, for a runbook that needs files kept next to it.

```sh run
pwd -P
echo "runbook: $PAULRUN_RUNBOOK_DIR"
```
