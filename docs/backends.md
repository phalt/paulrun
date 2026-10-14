# 🔌 Backends

A backend runs `run` blocks for one or more languages. paulrun comes with two, for shell and Python, and other languages can be added by any package.

Run `paulrun backends` to see which backends are installed, the languages each one runs, and the package it comes from:

```
python  python, py       paulrun.backends.python:PythonBackend (paulrun 0.1.0)
shell   sh, bash, shell  paulrun.backends.shell:ShellBackend (paulrun 0.1.0)
```

## Built-in backends

### shell

Languages: `sh`, `bash`, `shell`. Needs `bash`.

Each block runs as one `bash` script that stops at the first command that fails, as if it began with `set -eo pipefail`. `check` finds syntax errors with `bash -n`, and adds [shellcheck](install.md#optional-shellcheck) warnings if it's installed. See [Shell blocks](runbook-format.md#shell-blocks).

### python

Languages: `python`, `py`. Needs nothing extra.

Each block runs as its own script, with the command in the runbook's [`python`](runbook-format.md#python-blocks) frontmatter key, or with the Python paulrun runs on. `check` finds syntax errors by compiling each block. See [Python blocks](runbook-format.md#python-blocks).

## Writing a backend

A backend is a plain class with a `name`, the `languages` it runs, and two methods: `validate()` checks a block without running it, and `run()` runs it. It doesn't need a base class; it only has to look like this protocol, from `paulrun.backends`:

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

`paulrun check` calls `validate()` on every block in the backend's languages, and so does `paulrun run`, before anything runs. It returns a list of `Problem`s:

```python
@dataclass(frozen=True)
class Problem:
    """Something a backend found wrong with a block."""

    message: str
    line: int | None = None  # line in the block, counting its first line as 1; None if it's about the whole block
    warning: bool = False  # warnings are reported but don't stop the runbook running
```

- **Lines count from the block's first line**, as 1. paulrun turns them into lines in the runbook, so `check` points at the right place.
- **An error stops a run** before anything runs. A warning is shown, and the run carries on.
- **The code is as written**, with `<NAME>` placeholders still in it. Before checking it, swap each one for something your language accepts. The built-in backends use the placeholder's bare name, which is a plain word in shell and a plain name in Python:

    ```python
    from paulrun.inputs import PLACEHOLDER

    script = PLACEHOLDER.sub(lambda match: match.group(1), code)
    ```

- **Check that what `run()` needs is installed.** `paulrun run` always validates first, so an error here is far friendlier than `run()` failing to start.

### run()

`run()` gets:

- `code`: the block with every placeholder replaced by its value. Secrets are never replaced; they're only in `env`.
- `frontmatter`: the runbook's frontmatter, read-only, for a backend with settings of its own, like the Python backend's `python` key.
- `env`: the block's complete environment, including every input. Pass it on as it is.
- `cwd`: the folder paulrun was started from, where the block runs. See [Where blocks run](runbook-format.md#where-blocks-run).
- `output`: call it with each line the block prints, as soon as it's printed.

It returns the block's exit code, where `0` means it succeeded and anything else stops the run.

A backend never prints. paulrun shows each line, replaces secrets with `****`, and records it in the transcript, so a backend doesn't need to do any of that itself.

### stream()

Most backends run a command, and `stream()` does all of that for you:

```python
def stream(command: Sequence[str], *, env: Mapping[str, str], cwd: Path, output: Callable[[str], None]) -> int:
```

It runs `command`, passes each line it prints to `output` as it's printed, and returns its exit code. It's what the built-in backends use, and it gets the details right:

- **stdout and stderr are merged**, so lines are shown in the order they were printed.
- **The command shares paulrun's terminal**, so it can still ask for a password the way `git`, `ssh` and `gpg` do.
- **Ctrl-C works.** On the first press, the command gets the chance to stop by itself, and anything it prints on the way out is still shown. A second press kills it, and everything it started. Either way, once it's stopped, `stream()` raises `Interrupted` with its exit code, so the run can record how the block ended.

A backend that doesn't use `stream()` should do the same: once its block has stopped after Ctrl-C, raise `Interrupted(exit_code)`. paulrun records the block's exit code, then finishes the run as interrupted.

## Shipping your own backend

Anyone can publish a backend in their own package. Once it's installed alongside paulrun, it loads exactly like a built-in one.

Here's a complete backend for Node.js, in a package called `paulrun-node`:

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

`pyproject.toml` registers it under the `paulrun.backends` entry point group, which is how paulrun finds it:

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

With `pip`, install it into the same environment as paulrun. Then `paulrun backends` lists it:

```
node    js, javascript   paulrun_node:NodeBackend (paulrun-node 0.1.0)
python  python, py       paulrun.backends.python:PythonBackend (paulrun 0.1.0)
shell   sh, bash, shell  paulrun.backends.shell:ShellBackend (paulrun 0.1.0)
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

To test a backend, create it and call its methods directly, the way paulrun tests its own: call `run()` with `output=lines.append` and check the exit code and the lines, and call `validate()` on a broken block. See [paulrun's backend tests](https://github.com/phalt/paulrun/tree/main/tests/backends).

### Things to know

- **Each language can only have one backend.** If two installed backends claim the same language, paulrun stops with an error naming both. `paulrun backends` shows which languages are taken.
- **Frontmatter keys of your own get a `check` warning.** A backend can read its own settings from `frontmatter`, but `check` only knows paulrun's keys, so it warns about any other. The warning doesn't stop a run.

## Adding a backend to paulrun

A backend for a language lots of people use can ship with paulrun itself. Built-in backends load the same way as external ones, so it's the same code, in a different place:

1. **`paulrun/backends/<name>.py`**, implementing the protocol. [`shell.py`](https://github.com/phalt/paulrun/blob/main/paulrun/backends/shell.py) and [`python.py`](https://github.com/phalt/paulrun/blob/main/paulrun/backends/python.py) are good models: both use `stream()`, and swap placeholders before validating.
2. **One entry point line** in paulrun's `pyproject.toml`, next to the built-in ones:

    ```toml
    [project.entry-points."paulrun.backends"]
    shell = "paulrun.backends.shell:ShellBackend"
    python = "paulrun.backends.python:PythonBackend"
    ```

    Then run `make install`, and `uv run paulrun backends` should list it.

3. **`tests/backends/test_<name>.py`**, which really runs blocks in `tmp_path`, with no mocking. Skip the tests if the language isn't installed, e.g. `pytest.mark.skipif(shutil.which("ruby") is None, reason="ruby isn't installed")`. CI runs on GitHub's `ubuntu-latest`, which already has many languages; if yours isn't one of them, add a step to `.github/workflows/ci.yml` that installs it, so CI runs the tests rather than skipping them.
4. **A section on this page**, under [Built-in backends](#built-in-backends): its languages, what it needs installed, how it runs a block, and how `check` validates one.
5. **A CHANGELOG entry**, in both `CHANGELOG.md` and `docs/CHANGELOG.md`.

[CONTRIBUTING.md](https://github.com/phalt/paulrun/blob/main/CONTRIBUTING.md) has the rest: setting up, and what to run before opening a pull request.
