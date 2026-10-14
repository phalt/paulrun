---
title: Choice does not match pattern
inputs:
  - name: ENV
    description: Where to deploy
    pattern: '^[a-z]+$'
    choices: [staging, prod-eu]
---

## Only step

```sh run
echo "<ENV>"
```
