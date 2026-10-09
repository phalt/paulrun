---
title: Python example
description: Run Python blocks alongside shell ones.
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
---

# Python example

A fence marked `python run` (or `py run`) is run as a Python script:

```sh
VERSION=1.2.0 uv run paulrun go tests/runbooks/python-example.md
```

With no `python` key in the frontmatter, blocks run with the interpreter that's
running paulrun, so only the standard library is available. Set `python` to
any command to use another interpreter, for example:

```yaml
python: uv run python
```

Each block is its own script, so nothing is shared between blocks except the
environment. Inputs are substituted and exported, just like in shell blocks.

## Check the version

```python run
import os

version = "<VERSION>"
assert version == os.environ["VERSION"]
major, minor, patch = (int(part) for part in version.split("."))
print(f"Releasing {major}.{minor}.{patch}")
```

## Work out the next version

```py run
major, minor, patch = (int(part) for part in "<VERSION>".split("."))
print(f"Next version: {major}.{minor}.{patch + 1}")
```
