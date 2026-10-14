---
title: Choices example
description: Only accept one of a few values for an input.
inputs:
  - name: FE_SET
    description: Which frontend set to rebuild
    choices: [comms, billing, all]
    default: comms
---

# Choices example

An input with `choices` lists them at the prompt, and only takes one of them:

```sh
uv run paulrun tests/runbooks/choices-example.md
```

```
FE_SET (Which frontend set to rebuild) [comms] (comms, billing, all): everything
FE_SET must be one of: comms, billing, all
```

Type the choice itself, not its number. A value from the environment has to be
one of the choices too, or paulrun stops before anything runs. Choices work
with a `default`, which has to be one of them, and with a `pattern`, which
every choice has to match.

## Rebuild

```sh run
echo "Rebuilding the <FE_SET> frontend"
```
