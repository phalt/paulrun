---
title: Release clientele
description: Release a new version of clientele to GitHub, the docs site and PyPI.
output_path: logs/release-<VERSION>.md
python: uv run python
inputs:
  - name: VERSION
    description: The version to release, e.g. 2.3.2
    pattern: '^\d+\.\d+\.\d+$'
  - name: UV_PUBLISH_TOKEN
    description: PyPI API token for clientele
    secret: true
---

# ⚜️ Releasing clientele

This is how [clientele](https://github.com/phalt/clientele) releases a new
version. It lives in clientele's repository as `PUBLISHING.md`, and is run
from there:

```sh
paulrun go PUBLISHING.md --dry
paulrun go PUBLISHING.md
```

Before you start, add a `## <version>` section for the release to the top of
`CHANGELOG.md`, and copy it to `docs/CHANGELOG.md`. That change gets committed
with the version bump.

Each run is recorded in `logs/release-<version>.md`. Add `logs/` to
`.gitignore`, so a release's own record isn't committed with it.

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

## Update the version

clientele keeps its version in two places. `uv version` sets the one in
`pyproject.toml` and updates `uv.lock` to match. The one in
`clientele/settings.py` is shown in every generated client.

```sh run
uv version <VERSION>
```

```python run
import os
import re
from pathlib import Path

settings = Path("clientele/settings.py")
version = f'VERSION = "{os.environ["VERSION"]}"'
text, count = re.subn(r'^VERSION = ".*"$', version, settings.read_text(), flags=re.MULTILINE)
if count != 1:
    raise SystemExit(f"Expected one VERSION line in {settings}, found {count}")
settings.write_text(text)
print(version)
```

## Regenerate the test clients

The example clients show the version in their `MANIFEST.md` files, so they're
regenerated with the new one. Then the tests run against them.

```sh run
make generate-test-clients
make test
git status --short
```

The test clients' `MANIFEST.md` files should be the only generated files that
changed.

```confirm
Check the changes above: only the version, the changelog and the test
clients' MANIFEST.md files should have changed for <VERSION>.
```

## Commit and push

There's nothing to commit when rerunning a release that failed after this
step.

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
https://github.com/phalt/clientele/releases/new?tag=<VERSION>

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
