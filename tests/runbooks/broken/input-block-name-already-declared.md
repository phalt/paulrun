---
title: Input block whose name is already declared
inputs:
  - name: OTP
    description: Declared in the frontmatter
---

## Publish

```input
name: OTP
description: Declared again here
```

```sh run
echo "$OTP"
```
