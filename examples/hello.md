---
title: Say hello
inputs:
  - name: NAME
    description: Who to say hello to
---

# Say hello

A runbook is just markdown. paulrun runs the blocks marked `run`, shows the
`docstring` ones, and leaves everything else alone, like this paragraph.

## Greet

```docstring
Saying hello to <NAME>.
```

```sh run
echo "Hello, <NAME>!"
```

## Count the letters

```python run
import os

name = os.environ["NAME"]
print(f"{name} has {len(name)} letters")
```
