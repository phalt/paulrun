# 🔌 Backends

A backend runs `run` blocks for one or more languages. paulrun comes with two, for shell and Python, and other languages can be added by any package.

Run `paulrun backends` to see which backends are installed, the languages each one runs, and the package it comes from:

```
python  python, py       paulrun.backends.python:PythonBackend (paulrun 0.2.0)
shell   sh, bash, shell  paulrun.backends.shell:ShellBackend (paulrun 0.2.0)
```

## Built-in backends

| Backend | Languages | Needs | See |
|---|---|---|---|
| shell | `sh`, `bash`, `shell` | `bash` | [Shell blocks](runbook-format.md#shell-blocks) |
| python | `python`, `py` | nothing extra | [Python blocks](runbook-format.md#python-blocks) |

## Writing a backend

A backend is a plain class with a `name`, the `languages` it runs, and two methods: `validate()` checks a block, and `run()` runs it. It doesn't need a base class, only to match this protocol from `paulrun.backends`:

```python
class Backend(Protocol):
    """Runs `run` blocks for one or more languages.

    Backends are classes registered under the `paulrun.backends` entry point group. Each is created
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
        output: Callable[[str], None],
    ) -> int:
        """Run a block and return its exit code, where 0 means it succeeded.

        Call output with each line the block prints, without its newline, as soon as it's printed.
        Don't print anything directly; paulrun owns the terminal. frontmatter is the runbook's
        frontmatter, read-only. env is the block's complete environment and cwd is where it runs.
        """
```

Everything a backend needs is in `paulrun.backends` (`Problem`, `stream` and `Interrupted`) and `paulrun.inputs` (`PLACEHOLDER`).

### validate()

`paulrun check` and `paulrun run` call `validate()` on every block before anything runs. It returns a list of `Problem`s:

```python
@dataclass(frozen=True)
class Problem:
    """Something a backend found wrong with a block."""

    message: str
    line: int | None = None  # line in the block, counting its first line as 1; None if it's about the whole block
    warning: bool = False  # warnings are reported but don't stop the runbook running
```

- **Lines count from the block's first line**, as 1. paulrun turns them into lines in the runbook.
- **An error stops the run**; a warning is only shown.
- **The code still has its `<NAME>` placeholders.** Swap each for something your language accepts before checking it. The built-in backends use the bare name:

    ```python
    from paulrun.inputs import PLACEHOLDER

    script = PLACEHOLDER.sub(lambda match: match.group(1), code)
    ```

- **Check that what `run()` needs is installed**, so a missing tool is reported before anything runs.

### run()

`run()` gets:

- `code`: the block with its placeholders filled in. Secrets are only in `env`.
- `frontmatter`: the runbook's frontmatter, read-only, for settings of your own.
- `env`: the block's complete environment. Pass it on as it is.
- `cwd`: where the block runs, the folder paulrun was started from.
- `output`: call it with each line the block prints, as it's printed.

It returns the block's exit code. A backend never prints: paulrun shows each line, masks secrets and records the transcript.

### stream()

Most backends run a command, and `stream()` does all of that for you:

```python
def stream(command: Sequence[str], *, env: Mapping[str, str], cwd: Path, output: Callable[[str], None]) -> int:
```

It runs `command`, passes each line to `output` as it's printed, and returns the exit code. The built-in backends use it, because it gets the details right:

- **stdout and stderr are merged**, in the order they were printed.
- **The command shares paulrun's terminal**, so it can still ask for a password.
- **Ctrl-C works.** The first press lets the command stop by itself; a second kills it and everything it started. Then `stream()` raises `Interrupted` with the exit code.

A backend that doesn't use `stream()` should also raise `Interrupted(exit_code)` once its block has stopped after Ctrl-C.

## Shipping your own backend

Anyone can publish a backend in their own package, and once it's installed alongside paulrun, it loads like a built-in one. Here's a complete backend for Node.js, in a package called `paulrun-node`:

```
paulrun-node/
  pyproject.toml
  paulrun_node/
    __init__.py
```

`paulrun_node/__init__.py`:

```python
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from paulrun.backends import Problem, stream
from paulrun.inputs import PLACEHOLDER


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

`pyproject.toml` registers it under the `paulrun.backends` entry point group:

```toml
[project]
name = "paulrun-node"
version = "0.1.0"
dependencies = ["paulrun>=0.1.0"]

[project.entry-points."paulrun.backends"]
node = "paulrun_node:NodeBackend"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Install it alongside paulrun:

```sh
uv tool install paulrun --with paulrun-node     # once it's on PyPI
uv tool install paulrun --with ./paulrun-node   # from a local folder, while you work on it
```

With `pip`, install it into paulrun's environment. Then `paulrun backends` lists it:

```
node    js, javascript   paulrun_node:NodeBackend (paulrun-node 0.1.0)
python  python, py       paulrun.backends.python:PythonBackend (paulrun 0.2.0)
shell   sh, bash, shell  paulrun.backends.shell:ShellBackend (paulrun 0.2.0)
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

To test a backend, call its methods directly: `run()` with `output=lines.append`, then check the exit code and lines, and `validate()` on a broken block. See [paulrun's backend tests](https://github.com/phalt/paulrun/tree/main/tests/backends).

### Things to know

- **Each language can only have one backend.** If two claim the same language, paulrun stops with an error naming both.
- **Frontmatter keys of your own get a `check` warning**, since `check` only knows paulrun's keys. It doesn't stop a run.

## Adding a backend to paulrun

A backend for a widely used language can ship with paulrun itself. It's the same code, in a different place:

1. **`paulrun/backends/<name>.py`**, implementing the protocol. [`shell.py`](https://github.com/phalt/paulrun/blob/main/paulrun/backends/shell.py) and [`python.py`](https://github.com/phalt/paulrun/blob/main/paulrun/backends/python.py) are good models.
2. **One entry point line** in paulrun's `pyproject.toml`, next to the built-in ones:

    ```toml
    [project.entry-points."paulrun.backends"]
    shell = "paulrun.backends.shell:ShellBackend"
    python = "paulrun.backends.python:PythonBackend"
    ```

    Then run `make install`, and `uv run paulrun backends` should list it.

3. **`tests/backends/test_<name>.py`**, which really runs blocks in `tmp_path`, skipped if the language isn't installed, e.g. `pytest.mark.skipif(shutil.which("ruby") is None, reason="ruby isn't installed")`. If GitHub's `ubuntu-latest` doesn't have the language, add a step to `.github/workflows/ci.yml` that installs it.
4. **A row in [Built-in backends](#built-in-backends)**, and a section in [the runbook format](runbook-format.md#run-blocks) on how its blocks run.
5. **A CHANGELOG entry**, in both `CHANGELOG.md` and `docs/CHANGELOG.md`.

[CONTRIBUTING.md](https://github.com/phalt/paulrun/blob/main/CONTRIBUTING.md) has the rest: setting up, and what to run before opening a pull request.
