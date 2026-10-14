---
title: Default on a secret
inputs:
  - name: TOKEN
    description: The token
    secret: true
    default: s3cret
---

## Only step

```sh run
echo "$TOKEN"
```
