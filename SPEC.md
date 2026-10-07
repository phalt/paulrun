# Spec: paulrun

Status: draft, awaiting review
Version target: 0.1.0

## Objective

`paulrun` runs hand-written markdown runbooks.

A runbook is a normal markdown file a human can read and follow without paulrun installed. Fenced code blocks marked `run` are executed for you, `docstring` blocks are printed as you go, and `confirm` blocks pause for a manual step. Everything else is documentation and is ignored.

**User:** Paul. Published to PyPI with a proper README and docs so other people can use it if they want to.

**Why:** Release procedures (starting with clientele's PUBLISHING.md) get forgotten. Writing them down helped; making the written-down version executable fixes it.

### User stories

- As Paul, I run `paulrun check PUBLISHING.md` and get told about undeclared placeholders, bad frontmatter and broken code blocks before I run anything.
- As Paul, I run `paulrun go PUBLISHING.md --dry` and see exactly what would run, with inputs substituted, without anything executing.
- As Paul, I run `paulrun go PUBLISHING.md`, answer a couple of prompts, and the release happens end to end.
- As Paul, I open the transcript file afterwards and see every command that ran and what it printed.
- As a contributor, I add a backend for another language to `paulrun/backends/` in a PR, and it ships with the next paulrun release for everyone.
- As someone with a private backend, I register it from my own package's `pyproject.toml` and paulrun picks it up without a PR.

## Decisions

1. Local and interactive only. paulrun assumes a TTY; no CI mode.
2. Blocks always run with the runbook file's directory as the working directory.
3. Every input is checked for in the environment first. If `VERSION` is set, paulrun uses it and doesn't prompt.
4. MIT licence, same as clientele.

## Runbook format

This is the contract. Changes to it need sign-off (see Boundaries).

### Frontmatter

YAML between `---` lines at the top of the file. paulrun can read just the frontmatter without parsing the body.

```yaml
---
title: Publish clientele                  # required
description: Release a new version.        # optional
output_path: logs/release-<VERSION>.md     # optional
python: uv run python                      # optional, interpreter for python blocks
inputs:                                    # optional
  - name: VERSION                          # required, UPPER_SNAKE_CASE
    description: The version being released, e.g. 2.1.0   # required
    pattern: '^\d+\.\d+\.\d+$'             # optional, full-match regex
  - name: UV_PUBLISH_TOKEN
    description: PyPI API token
    secret: true                           # optional, default false
---
```

Core keys are `title`, `description`, `output_path`, `python` and `inputs`. Any other top-level key, and unknown input keys, are `check` warnings, not errors.

`python` is a command (split with `shlex`) used to run Python blocks, e.g. `uv run python` or `python3.12`. Defaults to the interpreter running paulrun. `check` errors if its first word isn't on `PATH`.

### Inputs

- Collected before any step runs: environment variable if set, otherwise a prompt. Secrets prompt with hidden input.
- `pattern` is validated on collection; a mismatch re-prompts (or fails, if the value came from the environment).
- Every input is exported as an environment variable to every block.
- Non-secret inputs are also substituted wherever `<NAME>` appears inside `run`, `docstring` and `confirm` blocks, and in `output_path`. Prose is never touched.
- Secrets are never substituted. Using `<SECRET_NAME>` anywhere is a `check` error.
- Placeholder syntax: `<` + `[A-Z][A-Z0-9_]*` + `>`.

### Steps

- Each `##` heading starts a step. The heading text is the step name.
- `###` and deeper are just prose inside the current step.
- A `run`, `docstring` or `confirm` block before the first `##` is a `check` error.

### Blocks

The fence info string decides what happens: first word is the language, a second word of `run` marks it executable.

| Fence | Behaviour |
|---|---|
| ```` ```docstring ```` | Printed during `go` |
| ```` ```confirm ```` | Printed, then waits for `y`. Anything else aborts the run |
| ```` ```<lang> run ```` | Executed by the backend registered for `<lang>` |
| anything else | Ignored. Documentation only |

A `run` block for a language with no registered backend is a `check` error.

## Backends

```python
class Backend(Protocol):
    name: str
    languages: tuple[str, ...]

    def validate(self, code: str) -> list[str]:
        """Return problems found in the block. Empty list means fine."""

    def run(self, code: str, *, frontmatter: Mapping[str, Any], env: dict[str, str], cwd: Path) -> Iterator[str] | int:
        """Run the block, streaming output. Final result is the exit code."""
```

The exact signature is decided in the plan; the requirements are: validation without execution, read-only access to the runbook's frontmatter, streamed output (so long commands aren't silent), and an exit code.

### Built-in backends

Backends live in `paulrun/backends/`, one module per backend, and ship with the paulrun package. New languages are added here by PR. Each built-in is registered in paulrun's own `pyproject.toml`, the same mechanism external backends use, so there's one loading path:

```toml
[project.entry-points."paulrun.backends"]
shell = "paulrun.backends.shell:ShellBackend"
python = "paulrun.backends.python:PythonBackend"
```

Adding a backend to paulrun means:

1. `paulrun/backends/<name>.py` implementing the protocol
2. One entry point line in `pyproject.toml`
3. `tests/backends/test_<name>.py` that actually runs a block (skipped if the interpreter isn't installed)
4. A section in `docs/backends.md`
5. A CHANGELOG entry

`CONTRIBUTING.md` spells this out.

### External backends

Anyone can ship a backend in their own package and register it from their own `pyproject.toml` under the same `paulrun.backends` group. Once that package is installed alongside paulrun, its backend loads like a built-in.

Two backends claiming the same language is an error at load time, naming both.

**shell**: languages `sh`, `bash`, `shell`. Runs as one `bash` script with `set -eo pipefail`. Validates with `bash -n`, plus `shellcheck` warnings if it's on `PATH`.

**python**: languages `python`, `py`. Runs blocks with the core `python` frontmatter command, defaulting to `sys.executable` (so with no key set, runbook Python is stdlib only). Each block is written to a temp file and run as `<command> <tempfile>`, so any interpreter command works. Blocks are validated with `compile()` after substituting dummy values; this uses paulrun's own interpreter, so syntax newer than the target interpreter supports won't be caught.

## Execution

`paulrun go RUNBOOK`:

1. Parse and validate (same as `check`). Errors stop here.
2. Collect inputs.
3. Print the title, step list and number of `run` blocks; ask to start.
4. For each step, in order: print the step name, then each block in order.
   - `docstring`: print it.
   - `confirm`: print it, wait for `y`.
   - `run`: print the substituted code, stream its output live, record exit code and duration.
5. A non-zero exit stops the run immediately. paulrun exits 1 and names the failed step.

`--step`: before each `run` block, after printing its code, ask `[y]es / [s]kip / [q]uit`. Skip moves on and is recorded in the transcript; quit ends the run as aborted.

`--dry`: steps 1 to 4, but nothing executes, `confirm` blocks don't wait, secrets aren't prompted for (shown as `****`), and no transcript is written. `--step` is ignored with `--dry`.

## Transcript (`output_path`)

Optional. Path is resolved relative to the runbook file, parent directories are created, and the file is **appended to** so a failed attempt and its rerun are both kept. Secret values are masked as `****` anywhere they appear, including command output.

Plain and boring on purpose:

```
--- paulrun PUBLISHING.md @ 2026-10-07T10:02:13+01:00
--- inputs: VERSION=2.3.2 UV_PUBLISH_TOKEN=****

=== Regenerate test clients ===
$ make generate-test-clients
<stdout and stderr, verbatim>
exit 0 (4.2s)

=== Create a new tag ===
$ git tag 2.3.2
exit 0 (0.1s)
confirm: Create a release from tag 2.3.2 ... -> yes

=== Publish documentation ===
$ make deploy-docs
skipped (--step)

--- finished: ok (3m12s)
```

A failed run ends with `--- finished: failed at "<step>" (exit N)`. A `confirm` answered with anything but `y`, or `q` under `--step`, ends with `--- finished: aborted at "<step>"`.

## Commands (CLI)

```
paulrun go RUNBOOK [--dry] [--step]   # run it
paulrun check RUNBOOK           # validate, exit 1 on errors, warnings printed
paulrun inputs RUNBOOK          # list declared inputs (frontmatter only)
paulrun backends                # list registered backends and their languages
paulrun --version
```

Exit codes: 0 success, 1 failure (check errors, failed block, aborted confirm), 2 usage error (Click default).

## Tech stack

Mirrors clientele.

- Python, `requires-python = ">=3.12"`, CI tests 3.12 and the latest release
- Build: hatchling. Package management: uv
- CLI: click, rich
- Parsing: markdown-it-py (fences give `.info` and `.content`), pyyaml for frontmatter
- Lint/format: ruff, line length 120, rules `F`, `E`, `W`, `I001`
- Types: ty
- Tests: pytest, pytest-cov
- Docs: mkdocs + mkdocs-material, deployed to GitHub Pages on the default `phalt.github.io/paulrun` URL (no CNAME)

Runtime dependencies: click, rich, markdown-it-py, pyyaml. Nothing else without asking.

## Project commands

Same Makefile shape as clientele, with `help` listing `##`-annotated targets.

```
make install        # uv sync
make test           # uv run pytest -vvv -x --cov=paulrun --cov-report=term-missing --cov-report=html --cov-config=pyproject.toml
make format         # uv run ruff format . && uv run ruff check --fix .
make ty             # uv run ty check .
make docs-serve     # uv run mkdocs serve
make deploy-docs    # uv run mkdocs build && uv run mkdocs gh-deploy
make release        # uv build && uv publish
make clean
make shell          # uv run ipython
```

## Project structure

Flat layout, like clientele.

```
paulrun/
  __init__.py
  settings.py          # VERSION = importlib.metadata.version("paulrun")
  cli.py               # click group: go, check, inputs, backends
  runbook.py           # frontmatter + body parsing into a Runbook model
  inputs.py            # collection, validation, substitution, masking
  runner.py            # executes steps, handles --dry
  transcript.py        # output_path writer
  backends/
    __init__.py        # Backend protocol, entry point loading
    shell.py
    python.py
tests/
  runbooks/            # fixture runbooks, valid and broken
  test_runbook.py
  test_inputs.py
  test_runner.py
  test_transcript.py
  test_backend_loading.py   # entry point loading, language conflicts
  test_cli.py
  backends/
    test_shell.py
    test_python.py
docs/
  index.md
  install.md
  runbook-format.md    # the contract above, written for humans
  cli.md
  backends.md          # including writing your own
  CHANGELOG.md
examples/
  hello.md             # smallest useful runbook
  clientele-publishing.md
.github/workflows/ci.yml
PUBLISHING.md          # paulrun releases itself with this
README.md
CHANGELOG.md
CONTRIBUTING.md
SECURITY.md
CODE_OF_CONDUCT.md
LICENSE
Makefile
mkdocs.yml
pyproject.toml
.python-version
```

Using `importlib.metadata` in `settings.py` means paulrun's own PUBLISHING.md only has one version to bump.

## Code style

Plain functions and frozen dataclasses. Type hints everywhere. No class where a function does.

```python
PLACEHOLDER = re.compile(r"<([A-Z][A-Z0-9_]*)>")


@dataclass(frozen=True)
class Input:
    name: str
    description: str
    pattern: str | None = None
    secret: bool = False


def substitute(text: str, values: dict[str, str]) -> str:
    """Replace <NAME> placeholders with their values. Unknown names are left alone."""
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
```

Output goes through a single `rich` console in `cli.py`; library modules return data or raise, they don't print.

## Testing strategy

- pytest, tests in `tests/` named `test_<module>.py`.
- Parsing and validation tested against fixture runbooks in `tests/runbooks/`, one fixture per error case.
- Each backend has its own test module in `tests/backends/`, actually running small blocks in `tmp_path`. They're fast; no mocking subprocess. Contributed backends follow the same pattern.
- CLI tested with Click's `CliRunner`, feeding prompt answers via `input=`.
- Transcript tested by running a fixture runbook twice and asserting both runs are in the file and secrets are masked.
- Coverage reported, no enforced threshold.
- CI (`ci.yml`): ruff check, ruff format --check, ty, pytest on push and PR.

## Boundaries

**Always:**
- Run `make format`, `make ty` and `make test` before committing
- Add a CHANGELOG entry for user-visible changes
- Update `docs/runbook-format.md` in the same change as any format behaviour

**Ask first:**
- Adding a runtime dependency
- Any change to the runbook format: frontmatter keys, fence semantics, placeholder syntax
- Adding CLI commands or flags beyond the ones listed here
- Anything in the Out of Scope list

**Never:**
- Execute a fence that isn't marked `run`
- Substitute a secret into code, or write an unmasked secret to the terminal or transcript
- Commit secrets or tokens
- Publish to PyPI or deploy docs without Paul doing it

## Out of scope for 0.1.0

- Resuming with `--from`
- Non-interactive / CI mode
- Backends beyond shell and Python
- File-edit blocks
- Any TUI

## Success criteria

- [ ] `paulrun check` passes on `examples/clientele-publishing.md` and fails, with a clear message, on each broken fixture in `tests/runbooks/`
- [ ] `paulrun check` errors on: missing `title`, input missing `name` or `description`, undeclared placeholder in a block, secret used as a placeholder, `run` block with no backend, `run` block before the first `##`
- [ ] `paulrun go --dry` prints every step with inputs substituted, executes nothing and writes no transcript
- [ ] `paulrun go` stops on the first non-zero exit and names the failed step
- [ ] `paulrun go --step` runs, skips or quits per block, and skips appear in the transcript
- [ ] With `python: <command>` set, Python blocks run under that command; `check` errors when the command isn't on `PATH`
- [ ] Built-in shell and Python backends load from `paulrun/backends/` via paulrun's own entry points
- [ ] An external backend registered via entry point shows up in `paulrun backends` and runs its blocks (tested with a backend defined in the test suite)
- [ ] `CONTRIBUTING.md` and `docs/backends.md` walk through adding a backend to paulrun and shipping an external one
- [ ] With `output_path` set, two runs append two transcripts to the same file, and no secret value appears anywhere in it
- [ ] The next clientele release is done with `paulrun go PUBLISHING.md`
- [ ] paulrun 0.1.0 is released to PyPI by running `paulrun go PUBLISHING.md` in its own repo
- [ ] README and the mkdocs site cover install, the runbook format, the CLI and writing a backend

## Open questions

None.
