---
title: Say where
description: Show where a book from the library runs, and where it's kept.
---

# Say where

A book in a runbook library. Point `RUNDOT_LIBRARY` at this folder, and it
runs by name from anywhere, in the folder you run it from:

```sh
cd /tmp
RUNDOT_LIBRARY=~/Projects/rundot/tests/library uv run --project ~/Projects/rundot rundot say-where
```

## Say where

`pwd` is the folder you ran rundot from. `RUNDOT_RUNBOOK_DIR` is the
library, where this book is kept.

```sh run
pwd -P
echo "kept in: $RUNDOT_RUNBOOK_DIR"
```
