---
title: Release paulrun
description: Release a new version of paulrun to GitHub, the docs site and PyPI.
output_path: logs/release-<VERSION>.md
inputs:
  - name: VERSION
    description: The version to release, e.g. 0.2.0
    pattern: '^\d+\.\d+\.\d+$'
  - name: UV_PUBLISH_TOKEN
    description: PyPI API token for paulrun
    secret: true
---

# 🏃‍♂️‍➡️📕 Releasing paulrun

paulrun releases itself with this runbook:

```sh
paulrun check PUBLISHING.md
paulrun PUBLISHING.md --dry
paulrun PUBLISHING.md
```

You can also follow it by hand: each step's commands are in the order they run.

Before you start, add a `## <version>` section for the release to the top of
`CHANGELOG.md`, and copy it to `docs/CHANGELOG.md`. That change gets committed
with the version bump.

Each run is recorded in `logs/release-<version>.md`, which git ignores.

## Check before releasing

Releases are made from an up-to-date `main`, with nothing left uncommitted
except the changelog, for a version that hasn't been released yet.

```sh run
git switch main
git pull origin main
git fetch --tags

if [ -n "$(git status --porcelain -- . ':!CHANGELOG.md' ':!docs/CHANGELOG.md' ':!logs')" ]; then
  echo "Commit or stash these changes first:"
  git status --short
  exit 1
fi
if git rev-parse --quiet --verify "refs/tags/<VERSION>" > /dev/null; then
  echo "Tag <VERSION> already exists"
  exit 1
fi
if ! grep -qx "## <VERSION>" CHANGELOG.md; then
  echo "CHANGELOG.md has no '## <VERSION>' section"
  exit 1
fi
```

## Run the checks

```sh run
make ty
make test
```

## Update the version

`pyproject.toml` holds paulrun's only copy of its version. `uv version` sets
it and updates `uv.lock` to match.

```sh run
uv version <VERSION>
uv run paulrun --version
```

## Commit and push

There's nothing to commit if the version and changelog were already
committed, e.g. for the first release, or when rerunning one that failed
after this step.

```sh run
if git diff --quiet HEAD; then
  echo "Nothing to commit"
else
  git commit -am "version <VERSION>"
fi
git push origin main
```

## Tag the release

```sh run
git tag <VERSION>
git push origin <VERSION>
```

## Create the GitHub release

These are the release notes, from `CHANGELOG.md`:

```python run
import os
import re
from pathlib import Path

version = re.escape(os.environ["VERSION"])
changelog = Path("CHANGELOG.md").read_text()
notes = re.search(rf"^## {version}\n(.*?)(?=^## |\Z)", changelog, re.MULTILINE | re.DOTALL)
print(notes.group(1).strip())
```

```confirm
Create a release on GitHub from tag <VERSION>:
https://github.com/phalt/paulrun/releases/new?tag=<VERSION>

Paste in the release notes above, and mark it as the latest release.
```

## Publish the documentation

Takes about 5-10 minutes to deploy fully.

```sh run
make deploy-docs
```

## Release to PyPI

`uv publish` uploads everything in `dist/`, so clear it out first.

```sh run
rm -rf dist
# uv publish reads the token from $UV_PUBLISH_TOKEN.
make release
```
