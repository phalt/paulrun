---
title: Default not one of the choices
inputs:
  - name: FE_SET
    description: Which frontend set to rebuild
    choices: [comms, billing, all]
    default: everything
---

## Only step

```sh run
echo "<FE_SET>"
```
