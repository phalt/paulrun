---
title: Default does not match pattern
inputs:
  - name: VERSION
    description: The version
    pattern: '^\d+\.\d+\.\d+$'
    default: latest
---

## Only step

```sh run
echo "<VERSION>"
```
