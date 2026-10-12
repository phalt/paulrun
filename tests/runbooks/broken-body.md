---
title: Broken body
description: Valid frontmatter, but a body that can't even be read.
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
  - name: PUBLISH_TOKEN
    description: Token for the package index
    secret: true
---

# Broken body

`paulrun inputs` reads only the frontmatter above, so it still lists the
inputs. `paulrun check` and `paulrun go` read the whole file, and stop at the
next line, which isn't valid UTF-8:

ÿþ not text

## A step
