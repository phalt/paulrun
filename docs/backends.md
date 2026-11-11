# 🔌 Backends

A backend runs `run` blocks for one or more languages. rundot comes with two, for shell and Python, and other languages can be added by any package.

Run `rundot backends` to see which backends are installed, the languages each one runs, and the package it comes from:

```
python  python, py       rundot.backends.python:PythonBackend (rundot 0.2.0)
shell   sh, bash, shell  rundot.backends.shell:ShellBackend (rundot 0.2.0)
```

## Built-in backends

| Backend | Languages | Needs | See |
|---|---|---|---|
| shell | `sh`, `bash`, `shell` | `bash` | [Shell blocks](runbook-format.md#shell-blocks) |
| python | `python`, `py` | nothing extra | [Python blocks](runbook-format.md#python-blocks) |

## Writing a backend

A backend is a plain class with a `name`, the `languages` it runs, and two methods: `validate()` checks a block, and `run()` runs it. It doesn't need a base class, only to match this protocol from `rundot.backends`:

```python
class Backend(Protocol):
    """Runs `run` blocks for one or more languages.

    Backends are classes registered under the `rundot.backends` entry point group. Each is created
    once, with no arguments, when backends are loaded.
    """

    # Read-only, so a backend can set them as plain class attributes.
    @property
    def name(self) -> str: ...

    @property
    def languages(self) -> tuple[str, ...]:
        """The fence languages this backend runs, e.g. ("sh", "bash")."""

    def validate(self, code: str) -> list[Problem]:
        """Return the problems found in a block, without running it. An empty list means it's fine.

        code is the block as written, so it can contain <NAME> placeholders. Replacing them with
        something this language accepts is up to the backend. Any error stops the runbook running;
        warnings are only reported.
        """

    def run(
        self,
        code: str,
        *,
        frontmatter: Mapping[str, Any],
        env: Mapping[str, str],
        cwd: Path,
        output: Output,
    ) -> int:
        """Run a block and return its exit code, where 0 means it succeeded.

        Call output with each line the block prints, without its newline, as soon as it's printed, and
        stderr=True for a line it wrote to stderr.
        Don't print anything directly; rundot owns the terminal. frontmatter is the runbook's
        frontmatter, read-only. env is the block's complete environment and cwd is where it runs.
        """
```

Everything a backend needs is in `rundot.backends` (`Problem`, `Output`, `stream` and `Interrupted`) and `rundot.inputs` (`PLACEHOLDER`).

### validate()

`rundot check` and `rundot run` call `validate()` on every block before anything runs. It returns a list of `Problem`s:

```python
@dataclass(frozen=True)
class Problem:
    """Something a backend found wrong with a block."""

    message: str
    line: int | None = None  # line in the block, counting its first line as 1; None if it's about the whole block
    warning: bool = False  # warnings are reported but don't stop the runbook running
```

- **Lines count from the block's first line**, as 1. rundot turns them into lines in the runbook.
- **An error stops the run**; a warning is only shown.
- **The code still has its `<NAME>` placeholders.** Swap each for something your language accepts before checking it. The built-in backends use the bare name:

    ```python
    from rundot.inputs import PLACEHOLDER

    script = PLACEHOLDER.sub(lambda match: match.group(1), code)
    ```

- **Check that what `run()` needs is installed**, so a missing tool is reported before anything runs.

### run()

`run()` gets:

- `code`: the block with its placeholders filled in. Secrets are only in `env`.
- `frontmatter`: the runbook's frontmatter, read-only, for settings of your own.
- `env`: the block's complete environment. Pass it on as it is.
- `cwd`: where the block runs, the folder rundot was started from.
- `output`: call it with each line the block prints, as it's printed. Pass `stderr=True` for a line the block wrote to stderr, and rundot marks it with a red `│`. `output(line)` alone is fine too: the line is shown like stdout.

It returns the block's exit code. A backend never prints: rundot shows each line, masks secrets and records the transcript.

### stream()

Most backends run a command, and `stream()` does all of that for you:

```python
def stream(command: Sequence[str], *, env: Mapping[str, str], cwd: Path, output: Callable[..., None]) -> int:
```

It runs `command`, passes each line to `output` as it's printed, and returns the exit code. The built-in backends use it, because it gets the details right:

- **stderr is marked.** Each line the command writes to stderr goes to `output` with `stderr=True`. stdout and stderr are read separately, so two lines written to them at almost the same moment can arrive in either order. Given an `output` that only takes the line, `stream()` merges them instead, in the order they were printed.
- **The command shares rundot's terminal**, so it can still ask for a password.
- **Ctrl-C works.** The first press lets the command stop by itself; a second kills it and everything it started. Then `stream()` raises `Interrupted` with the exit code.

A backend that doesn't use `stream()` should also raise `Interrupted(exit_code)` once its block has stopped after Ctrl-C.

## Shipping your own backend

Anyone can publish a backend in their own package, and once it's installed alongside rundot, it loads like a built-in one. Here's a complete backend for Node.js, in a package called `rundot-node`:

```
rundot-node/
  pyproject.toml
  rundot_node/
    __init__.py
```

`rundot_node/__init__.py`:

```python
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from rundot.backends import Problem, stream
from rundot.inputs import PLACEHOLDER


class NodeBackend:
    """Runs each block as a Node.js script."""

    name = "node"
    languages = ("js", "javascript")

    def validate(self, code: str) -> list[Problem]:
        if shutil.which("node") is None:
            return [Problem("node isn't installed")]
        # Swap each placeholder for its bare name, which is a plain identifier, so the code still parses.
        script = PLACEHOLDER.sub(lambda match: match.group(1), code)
        result = subprocess.run(["node", "--check"], input=script, capture_output=True, text=True)
        if result.returncode == 0:
            return []
        # node starts with where the error is, e.g. "[stdin]:3", and says what it is further down.
        where = re.match(r"\[stdin\]:(\d+)", result.stderr)
        errors = [line for line in result.stderr.splitlines() if line.startswith("SyntaxError: ")]
        return [Problem(errors[0] if errors else result.stderr.strip(), line=int(where.group(1)) if where else None)]

    def run(
        self,
        code: str,
        *,
        frontmatter: Mapping[str, Any],
        env: Mapping[str, str],
        cwd: Path,
        output: Callable[[str], None],
    ) -> int:
        return stream(["node", "-e", code], env=env, cwd=cwd, output=output)
```

`pyproject.toml` registers it under the `rundot.backends` entry point group:

```toml
[project]
name = "rundot-node"
version = "0.1.0"
dependencies = ["rundot>=0.1.0"]

[project.entry-points."rundot.backends"]
node = "rundot_node:NodeBackend"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Install it alongside rundot:

```sh
uv tool install rundot --with rundot-node     # once it's on PyPI
uv tool install rundot --with ./rundot-node   # from a local folder, while you work on it
```

With `pip`, install it into rundot's environment. Then `rundot backends` lists it:

```
node    js, javascript   rundot_node:NodeBackend (rundot-node 0.1.0)
python  python, py       rundot.backends.python:PythonBackend (rundot 0.2.0)
shell   sh, bash, shell  rundot.backends.shell:ShellBackend (rundot 0.2.0)
```

and runbooks can use it:

````markdown
---
title: Hello from Node
---

## Say hello

```js run
console.log(`Hello from Node ${process.version}`);
```
````

To test a backend, call its methods directly: `run()` with `output=lines.append`, then check the exit code and lines (or `output=lambda line, stderr=False: lines.append((line, stderr))` to check which stream each came from), and `validate()` on a broken block. See [rundot's backend tests](https://github.com/phalt/rundot/tree/main/tests/backends).

### Things to know

- **Each language can only have one backend.** If two claim the same language, rundot stops with an error naming both.
- **Frontmatter keys of your own get a `check` warning**, since `check` only knows rundot's keys. It doesn't stop a run.

## Adding a backend to rundot

A backend for a widely used language can ship with rundot itself. It's the same code, in a different place:

1. **`rundot/backends/<name>.py`**, implementing the protocol. [`shell.py`](https://github.com/phalt/rundot/blob/main/rundot/backends/shell.py) and [`python.py`](https://github.com/phalt/rundot/blob/main/rundot/backends/python.py) are good models.
2. **One entry point line** in rundot's `pyproject.toml`, next to the built-in ones:

    ```toml
    [project.entry-points."rundot.backends"]
    shell = "rundot.backends.shell:ShellBackend"
    python = "rundot.backends.python:PythonBackend"
    ```

    Then run `make install`, and `uv run rundot backends` should list it.

3. **`tests/backends/test_<name>.py`**, which really runs blocks in `tmp_path`, skipped if the language isn't installed, e.g. `pytest.mark.skipif(shutil.which("ruby") is None, reason="ruby isn't installed")`. If GitHub's `ubuntu-latest` doesn't have the language, add a step to `.github/workflows/ci.yml` that installs it.
4. **A row in [Built-in backends](#built-in-backends)**, and a section in [the runbook format](runbook-format.md#run-blocks) on how its blocks run.
5. **A CHANGELOG entry**, in both `CHANGELOG.md` and `docs/CHANGELOG.md`.

[CONTRIBUTING.md](https://github.com/phalt/rundot/blob/main/CONTRIBUTING.md) has the rest: setting up, and what to run before opening a pull request.
