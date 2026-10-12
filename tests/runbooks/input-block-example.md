---
title: Input block example
description: Ask for a value part way through a run, once it exists.
output_path: logs/pr-release.md
inputs:
  - name: VERSION
    description: The version being released, e.g. 1.2.0
    pattern: '^\d+\.\d+\.\d+$'
---

# Input block example

Most inputs are known before a run starts, so they go in the frontmatter. Some
only exist part way through: a pull request number GitHub gives you, or a
one-time code that expires in seconds. An `input` block asks for one when the
run reaches it:

```sh
VERSION=1.2.0 uv run paulrun go tests/runbooks/input-block-example.md
```

An `input` block takes the same keys as a frontmatter input. From then on, the
value is like any other input: in later blocks as `<NAME>` or `$NAME`, and a
secret is hidden as `****`.

## Open the pull request

```confirm
Open a pull request for <VERSION> on GitHub.
```

```input
name: PR
description: The number GitHub gave the pull request
pattern: '^\d+$'
```

```sh run
echo "Merging pull request <PR> for <VERSION>"
```

## Publish

```input
name: OTP
description: The code from your authenticator app
pattern: '^\d{6}$'
secret: true
```

```sh run
echo "Publishing <VERSION> with code $OTP"
```
