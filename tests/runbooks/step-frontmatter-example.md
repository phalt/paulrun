---
title: Step frontmatter example
description: A runbook that always asks before each run block.
step: true
---

# Step frontmatter example

`step: true` makes every run of this runbook work as if `--step` was given,
so nobody has to remember to pass it:

```sh
uv run paulrun tests/runbooks/step-frontmatter-example.md
```

paulrun shows each `run` block's code and then asks whether to run it, skip
it or quit, the same as `--step`. To run it straight through, without being
asked, pass `--no-step`:

```sh
uv run paulrun --no-step tests/runbooks/step-frontmatter-example.md
```

## Migrate the database

```sh run
echo "Migrating"
```

## Restart the service

```sh run
echo "Restarting"
```
