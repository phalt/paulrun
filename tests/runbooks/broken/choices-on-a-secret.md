---
title: Choices on a secret
inputs:
  - name: TOKEN
    description: The token
    secret: true
    choices: [one, two]
---

## Only step

```sh run
echo "$TOKEN"
```
