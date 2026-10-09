---
title: Two steps
---

# Two steps

A shell-only runbook for watching `paulrun go` stream output, in the runbook's own directory.

## Count slowly

```sh run
for i in 1 2 3; do echo "$i"; sleep 0.2; done
```

## Say where

```sh run
pwd -P
```
