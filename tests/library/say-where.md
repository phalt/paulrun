---
title: Say where
description: Show where a book from the library runs, and where it's kept.
---

# Say where

A book in a runbook library. Point `PAULRUN_LIBRARY` at this folder, and it
runs by name from anywhere, in the folder you run it from:

```sh
cd /tmp
PAULRUN_LIBRARY=~/Projects/paulrun/tests/library uv run --project ~/Projects/paulrun paulrun go say-where
```

## Say where

`pwd` is the folder you ran paulrun from. `PAULRUN_RUNBOOK_DIR` is the
library, where this book is kept.

```sh run
pwd -P
echo "kept in: $PAULRUN_RUNBOOK_DIR"
```
