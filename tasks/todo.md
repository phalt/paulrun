# paulrun 0.1.0 tasks

Plan: [tasks/plan.md](plan.md). Spec: [specs/SPEC.md](../specs/SPEC.md).

Every task also clears the standing bar: `make format`, `make ty` and `make test` clean, CHANGELOG entry for anything user-visible, and `docs/runbook-format.md` updated alongside any format behaviour (once it exists).

---

## Phase 1: Foundation

## Task 1: Package skeleton with `paulrun --version`

**Description:** Create the flat `paulrun/` package and `pyproject.toml` mirroring clientele: hatchling build, `requires-python = ">=3.12"`, runtime deps (click, rich, markdown-it-py, pyyaml), dev dependency group (pytest, pytest-cov, ruff, ty, mkdocs, mkdocs-material, ipython), ruff config (line length 120, `F`, `E`, `W`, `I001`), pytest and coverage config, the `paulrun` console script, and empty `paulrun.backends` entry point group. `settings.py` reads `VERSION` from `importlib.metadata`. `cli.py` is a Click group with `--version` only.

**Acceptance criteria:**
- [ ] `uv run paulrun --version` prints `paulrun, version 0.1.0`
- [ ] `uv run paulrun --help` lists the group with no commands yet
- [ ] `uv build` produces a wheel and sdist

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_cli.py`
- [ ] Build succeeds: `uv build`

**Dependencies:** None

**Files likely touched:**
- `pyproject.toml`
- `paulrun/__init__.py`
- `paulrun/settings.py`
- `paulrun/cli.py`
- `tests/test_cli.py`

**Estimated scope:** Medium

## Task 2: Dev tooling and CI, matching clientele

**Description:** Add the clientele-shaped Makefile (`help`, `install`, `test`, `format`, `ty`, `docs-serve`, `deploy-docs`, `release`, `clean`, `shell`), `.python-version` (`3.14`), `.gitignore`, MIT `LICENSE`, and `.github/workflows/ci.yml` (checkout, setup-python matrix, setup-uv with cache, `uv sync --frozen`, ruff format check, ruff check, ty, pytest with coverage). Commit `uv.lock`.

**Acceptance criteria:**
- [ ] `make help` lists every target with its description
- [ ] `make install && make test && make ty && make format` all pass locally
- [ ] CI workflow passes on a push to `main`

**Verification:**
- [ ] Tests pass: `make test`
- [ ] Manual check: CI run green on GitHub

**Dependencies:** Task 1

**Files likely touched:**
- `Makefile`
- `.python-version`
- `.gitignore`
- `LICENSE`
- `.github/workflows/ci.yml`

**Estimated scope:** Small (config only)

## Task 3: Runbook parser

**Description:** `runbook.py` parses a file into an immutable `Runbook`: raw frontmatter dict, `title`, `description`, `output_path`, `python`, parsed `Input` list, and ordered `Step`s (name from each `##` heading) containing `Block`s (kind: `docstring` / `confirm` / `run`, language, content, source line). Uses markdown-it-py fence tokens (`.info`, `.content`, `.map`) and pyyaml for frontmatter. Blocks before the first `##` are kept in a preamble so validation can flag them later. A `read_frontmatter(path)` function reads only the frontmatter, stopping at the closing `---`. Parsing does not validate beyond "is this YAML a mapping"; validation is Task 10.

**Acceptance criteria:**
- [ ] The clientele example runbook parses into 6 steps with the expected block kinds and languages
- [ ] Plain fences (```` ```sh ````, ```` ```toml ````) are not blocks; ```` ```sh run ```` is
- [ ] `read_frontmatter` never reads past the closing `---` (tested with a body that would fail to parse)

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_runbook.py`

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/runbook.py`
- `tests/test_runbook.py`
- `tests/runbooks/clientele_publishing.md`
- `tests/runbooks/minimal.md`

**Estimated scope:** Medium

### Checkpoint 1: Foundation
- [ ] `make test`, `make ty`, `make format` clean; CI green on `main`
- [ ] Parser handles the clientele example runbook

---

## Phase 2: Walking skeleton

## Task 4: Backend protocol, entry point loader, shell backend

**Description:** `backends/__init__.py` defines the `Backend` protocol and `load_backends(entry_points=None) -> dict[str, Backend]` keyed by language, raising a clear error naming both backends when two claim the same language. Settle the exact `run()` shape here (a generator of output lines that returns the exit code, or similar) and record it in the protocol docstring. `backends/shell.py` runs a block as one `bash` script with `set -eo pipefail` via `Popen`, stdout+stderr merged, stdin inherited, lines yielded as they arrive. `validate()` runs `bash -n`. Registered in `pyproject.toml`.

**Acceptance criteria:**
- [ ] `load_backends()` returns the shell backend for `sh`, `bash` and `shell`
- [ ] A failing command mid-block stops the block with that command's exit code; a failure inside a pipe is caught
- [ ] Two fake backends claiming one language raise an error naming both

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_backend_loading.py tests/backends/test_shell.py`

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/backends/__init__.py`
- `paulrun/backends/shell.py`
- `pyproject.toml`
- `tests/test_backend_loading.py`
- `tests/backends/test_shell.py`

**Estimated scope:** Medium

## Task 5: Runner and `paulrun go` (shell blocks only)

**Description:** `runner.py` walks a `Runbook`'s steps and runs each `run` block through its backend, with the runbook's directory as `cwd`. It emits events (step started, block code, output line, block finished with exit code and duration, run finished) to a sink, so the CLI can print them and the transcript can later record them from the same stream. Block env sets `PYTHONUNBUFFERED=1`, `GIT_PAGER=cat`, `PAGER=cat`. `cli.py` adds `go RUNBOOK` printing events with rich (`markup=False, highlight=False` for output lines). Stops on the first non-zero exit.

**Acceptance criteria:**
- [ ] Output from a slow block (e.g. `for i in 1 2 3; do echo $i; sleep 0.2; done`) appears line by line, not all at the end
- [ ] Blocks run in the runbook's directory regardless of where `paulrun` is invoked
- [ ] A failing block stops the run; later steps don't run

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py`
- [ ] Manual check: run a two-step shell runbook from another directory and watch output stream

**Dependencies:** Tasks 3, 4

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_runner.py`
- `tests/test_cli.py`
- `tests/runbooks/two_steps.md`

**Estimated scope:** Medium

### Checkpoint 2: Walking skeleton
- [ ] `paulrun go` on a two-step shell runbook streams output live and stops on failure
- [ ] Review with Paul before widening

---

## Phase 3: Core features

## Task 6: Inputs: declare, collect, validate, substitute, mask

**Description:** `inputs.py` holds the `Input` model, `PLACEHOLDER` regex, `collect(inputs, env, prompter)` (environment first, then prompt; hidden prompt for secrets; `pattern` full-match with re-prompt, or failure if the bad value came from the environment), `substitute(text, values)` for non-secret inputs only, and `mask(text, secrets)`. The runner exports every input to block env and substitutes non-secret placeholders into `run` block code. A `Prompter` protocol (with a Click-backed implementation in `cli.py`) makes prompts injectable for tests.

**Acceptance criteria:**
- [ ] An input set in the environment is used without prompting; a pattern mismatch from the environment fails with a clear message
- [ ] `<VERSION>` in a `run` block is substituted before execution; a secret is available as `$NAME` but never substituted
- [ ] `mask()` replaces every occurrence of every secret value with `****`

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_inputs.py tests/test_runner.py`

**Dependencies:** Task 5

**Files likely touched:**
- `paulrun/inputs.py`
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_inputs.py`
- `tests/test_runner.py`

**Estimated scope:** Medium

## Task 7: `docstring` and `confirm` blocks, start prompt, exit codes

**Description:** The runner prints `docstring` blocks and pauses on `confirm` blocks (both with placeholder substitution). Before running, `go` prints the title, step list and `run` block count and asks to start. Any answer other than `y` to a `confirm` or the start prompt ends the run as aborted. Exit codes: 0 success, 1 for failed block or abort.

**Acceptance criteria:**
- [ ] `docstring` text is printed with inputs substituted
- [ ] Answering `n` to a `confirm` stops the run, exits 1, and later steps don't run
- [ ] Declining the start prompt runs nothing and exits 1

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py`

**Dependencies:** Task 6

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_runner.py`
- `tests/test_cli.py`

**Estimated scope:** Small

## Task 8: `--dry`

**Description:** `go --dry` walks the runbook exactly like a real run but executes nothing: `run` blocks are printed with inputs substituted, `confirm` blocks are printed without waiting, the start prompt is skipped, and secrets aren't prompted for (shown as `****`).

**Acceptance criteria:**
- [ ] `go --dry` on a runbook whose blocks would create files creates nothing
- [ ] Every `run` block is printed with non-secret inputs substituted
- [ ] No prompt for secret inputs; non-secret inputs still collected

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py`

**Dependencies:** Task 7

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_runner.py`
- `tests/test_cli.py`

**Estimated scope:** Small

## Task 9: Python backend and the `python:` frontmatter key

**Description:** `backends/python.py` handles `python` and `py`. It reads the core `python` frontmatter key (split with `shlex`), defaulting to `sys.executable`, writes the block to a temp file and runs `<command> <tempfile>` with the same streaming model as the shell backend. `validate()` runs `compile()` on the block after replacing placeholders with dummy values. Registered in `pyproject.toml`.

**Acceptance criteria:**
- [ ] A Python block runs with `sys.executable` when no `python` key is set
- [ ] With `python: <command>` set, blocks run under that command (tested with a stub interpreter script in `tmp_path`)
- [ ] A Python block that raises exits non-zero and stops the run

**Verification:**
- [ ] Tests pass: `uv run pytest tests/backends/test_python.py`

**Dependencies:** Task 5

**Files likely touched:**
- `paulrun/backends/python.py`
- `pyproject.toml`
- `tests/backends/test_python.py`

**Estimated scope:** Small

## Task 10: Validation and `paulrun check`

**Description:** `validate(runbook, backends) -> Report` collects errors and warnings with line numbers, and `go` calls it first. Errors: missing `title`; input missing `name` or `description`; input name not UPPER_SNAKE_CASE; invalid `pattern` regex; undeclared placeholder in a `run`/`docstring`/`confirm` block or `output_path`; secret used as a placeholder; `run` block with no backend; `run`/`docstring`/`confirm` block before the first `##`; `python` command not on `PATH`; backend `validate()` failures (`bash -n`, `compile()`). Warnings: unknown top-level keys, unknown input keys, declared-but-unused inputs, `shellcheck` findings when it's installed. `check RUNBOOK` prints the report and exits 1 on any error.

**Acceptance criteria:**
- [ ] Each error case above has a broken fixture runbook and a test asserting the message and line number
- [ ] `paulrun check` exits 0 on the clientele example and 1 on every broken fixture
- [ ] `paulrun go` refuses to start on a runbook with errors

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_validate.py tests/test_cli.py`
- [ ] Manual check: `uv run paulrun check tests/runbooks/clientele_publishing.md`

**Dependencies:** Tasks 6, 9

**Files likely touched:**
- `paulrun/validate.py`
- `paulrun/cli.py`
- `tests/test_validate.py`
- `tests/runbooks/broken/*.md`
- `tests/test_cli.py`

**Estimated scope:** Medium

### Checkpoint 3: Core features
- [ ] `paulrun check` and `paulrun go --dry` work on the clientele example runbook
- [ ] All `check` error cases from the spec covered by fixture tests

---

## Phase 4: Remaining features

## Task 11: `--step`

**Description:** `go --step` asks `[y]es / [s]kip / [q]uit` after printing each `run` block's code. Skip moves on; quit ends the run as aborted (exit 1). Ignored with `--dry`. Skips are emitted as events so Task 12 can record them.

**Acceptance criteria:**
- [ ] `y` runs the block, `s` skips it and the run continues, `q` aborts with exit 1
- [ ] `--dry --step` behaves exactly like `--dry`

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py`

**Dependencies:** Task 10

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_runner.py`
- `tests/test_cli.py`

**Estimated scope:** Small

## Task 12: Transcript (`output_path`)

**Description:** `transcript.py` subscribes to runner events and appends the plain transcript format from the spec to `output_path`: run header with timestamp and masked inputs, `=== step ===` lines, `$ code`, verbatim output, `exit N (Xs)`, confirm answers, `skipped (--step)`, and the `--- finished:` line for ok, failed and aborted. Path has placeholders substituted, is resolved relative to the runbook, and parent directories are created. All text is masked before writing. Not written under `--dry`.

**Acceptance criteria:**
- [ ] Two runs append two complete transcripts to the same file
- [ ] A secret value echoed by a block never appears in the file
- [ ] Failed, aborted and skipped runs produce the right finish/skip lines; `--dry` writes nothing

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_transcript.py`

**Dependencies:** Task 11

**Files likely touched:**
- `paulrun/transcript.py`
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_transcript.py`

**Estimated scope:** Medium

## Task 13: `paulrun inputs`, `paulrun backends`, external backend test

**Description:** `inputs RUNBOOK` lists declared inputs (name, description, pattern, secret) using `read_frontmatter` only. `backends` lists loaded backends, their languages and where each came from (entry point value). Add a test that injects a fake external backend through `load_backends(entry_points=...)` and runs one of its blocks end to end.

**Acceptance criteria:**
- [ ] `paulrun inputs` works on a runbook whose body is deliberately malformed
- [ ] `paulrun backends` lists shell and python with their languages
- [ ] An injected external backend shows up in `backends` and runs its block via `go`

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_cli.py tests/test_backend_loading.py`

**Dependencies:** Task 10

**Files likely touched:**
- `paulrun/cli.py`
- `tests/test_cli.py`
- `tests/test_backend_loading.py`

**Estimated scope:** Small

### Checkpoint 4: Feature complete
- [ ] Every code-level success criterion in the spec has a passing test
- [ ] Review with Paul

---

## Phase 5: Docs and dogfooding

## Task 14: mkdocs site

**Description:** `mkdocs.yml` mirroring clientele's material theme setup (light/dark palette toggle, code copy, search, nav tabs), `repo_url` to phalt/paulrun, default GitHub Pages URL. Pages: `index.md`, `install.md`, `runbook-format.md` (the full contract, written for humans, including the non-interactive and secret-masking caveats), `cli.md` (every command, flag and exit code).

**Acceptance criteria:**
- [ ] `make docs-serve` renders every page with working nav
- [ ] `runbook-format.md` covers every frontmatter key, fence type, placeholder rule and the transcript format
- [ ] `uv run mkdocs build --strict` passes

**Verification:**
- [ ] Build succeeds: `uv run mkdocs build --strict`
- [ ] Manual check: Paul skims the rendered site

**Dependencies:** Task 10

**Files likely touched:**
- `mkdocs.yml`
- `docs/index.md`
- `docs/install.md`
- `docs/runbook-format.md`
- `docs/cli.md`

**Estimated scope:** Medium

## Task 15: README, CONTRIBUTING, CHANGELOG and project docs

**Description:** README (what it is, install with `uv tool install paulrun`, a 30-second example, link to docs, macOS/Linux note). `docs/backends.md` (protocol, built-ins, adding a backend to paulrun step by step, shipping an external one). `CONTRIBUTING.md` in clientele's shape, including the AI disclosure and the backend checklist. `CHANGELOG.md` with the 0.1.0 entry, mirrored into `docs/CHANGELOG.md`. `SECURITY.md` and `CODE_OF_CONDUCT.md` copied from clientele with names swapped.

**Acceptance criteria:**
- [ ] README example runs as written
- [ ] `CONTRIBUTING.md` and `docs/backends.md` walk through adding a backend to paulrun and shipping an external one
- [ ] `mkdocs build --strict` still passes with the new pages in nav

**Verification:**
- [ ] Build succeeds: `uv run mkdocs build --strict`
- [ ] Manual check: Paul reads the README

**Dependencies:** Tasks 13, 14

**Files likely touched:**
- `README.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `docs/backends.md`
- `docs/CHANGELOG.md`
- `SECURITY.md`, `CODE_OF_CONDUCT.md` (copied)

**Estimated scope:** Medium (mostly prose)

## Task 16: Examples and paulrun's own PUBLISHING.md

**Description:** `examples/hello.md` (smallest useful runbook: one input, a docstring, a shell block, a Python block), `examples/clientele-publishing.md` (the reworked clientele runbook with `output_path`), and `PUBLISHING.md` at the repo root for releasing paulrun itself (bump version, `make install`, commit, tag, push, confirm GitHub release, `make deploy-docs`, `make release`). A test runs `paulrun check` against every file in `examples/` and the root `PUBLISHING.md`.

**Acceptance criteria:**
- [ ] `paulrun check` passes on all examples and `PUBLISHING.md` (enforced by a test)
- [ ] `paulrun go examples/hello.md` runs end to end
- [ ] `paulrun go PUBLISHING.md --dry` shows a sensible release for a test version

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_examples.py`
- [ ] Manual check: `uv run paulrun go PUBLISHING.md --dry`

**Dependencies:** Task 15

**Files likely touched:**
- `examples/hello.md`
- `examples/clientele-publishing.md`
- `PUBLISHING.md`
- `tests/test_examples.py`

**Estimated scope:** Small

### Checkpoint 5: Ready to release (Paul only)
- [ ] Paul releases clientele with `paulrun go PUBLISHING.md`
- [ ] Paul releases paulrun 0.1.0 with its own PUBLISHING.md
- [ ] Docs deployed to `phalt.github.io/paulrun`
