---
title: Step example
description: Choose, block by block, what runs.
---

# Step example

With `--step`, paulrun shows each `run` block's code and then asks what to do:

```sh
uv run paulrun go --step tests/runbooks/step-example.md
```

- `y` runs the block.
- `s` skips it, and the run carries on with the next one.
- `q` quits, ending the run as aborted.

Any other answer asks again. `docstring` and `confirm` blocks work as usual,
and `--step` is ignored with `--dry`, since nothing runs then anyway.

## Build

```sh run
echo "Building"
```

## Publish

```sh run
echo "Publishing"
```

## Announce

```sh run
echo "Announcing"
```
