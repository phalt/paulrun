# paulrun 0.1.0 tasks

Plan: [tasks/plan.md](plan.md). Spec: [specs/SPEC.md](../specs/SPEC.md).

Every task also clears the standing bar: `make format`, `make ty` and `make test` clean, CHANGELOG entry for anything user-visible, and `docs/runbook-format.md` updated alongside any format behaviour (once it exists).

---

## Phase 1: Foundation

## Task 1: Package skeleton with `paulrun --version`

**Description:** Create the flat `paulrun/` package and `pyproject.toml` mirroring clientele: hatchling build, `requires-python = ">=3.12"`, runtime deps (click, rich, markdown-it-py, pyyaml), dev dependency group (pytest, pytest-cov, ruff, ty, mkdocs, mkdocs-material, ipython), ruff config (line length 120, `F`, `E`, `W`, `I001`), pytest and coverage config, the `paulrun` console script, and empty `paulrun.backends` entry point group. `settings.py` reads `VERSION` from `importlib.metadata`. `cli.py` is a Click group with `--version` only.

**Acceptance criteria:**
- [x] `uv run paulrun --version` prints `paulrun, version 0.1.0`
- [x] `uv run paulrun --help` lists the group with no commands yet
- [x] `uv build` produces a wheel and sdist

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_cli.py`
- [x] Build succeeds: `uv build`

**Dependencies:** None

**Files likely touched:**
- `pyproject.toml`
- `paulrun/__init__.py`
- `paulrun/settings.py`
- `paulrun/cli.py`
- `tests/test_cli.py`

**Estimated scope:** Medium

## Task 2: Dev tooling and CI, matching clientele

**Description:** Add the clientele-shaped Makefile (`help`, `install`, `test`, `format`, `ty`, `docs-serve`, `deploy-docs`, `release`, `clean`, `shell`), `.python-version` (`3.14`), `.gitignore`, MIT `LICENSE`, and `.github/workflows/ci.yml` (checkout, setup-python matrix `3.12`, `3.13`, `3.14`, `3.15-dev` as in clientele, setup-uv with cache, `uv sync --frozen`, ruff format check, ruff check, ty, pytest with coverage reported in the log; no Codecov upload). Commit `uv.lock`.

**Acceptance criteria:**
- [x] `make help` lists every target with its description
- [x] `make install && make test && make ty && make format` all pass locally
- [x] CI workflow passes on a push to `main`

**Verification:**
- [x] Tests pass: `make test`
- [x] Manual check: CI run green on GitHub

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
- [x] `tests/runbooks/all_features.md` parses into the expected steps, block kinds, languages and line numbers
- [x] Plain fences (```` ```sh ````, ```` ```toml ````) are not blocks; ```` ```sh run ```` is
- [x] `read_frontmatter` never reads past the closing `---` (tested with a body that would fail to parse)

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runbook.py`

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/runbook.py`
- `paulrun/inputs.py` (the `Input` dataclass only; Task 6 fills in the module)
- `tests/test_runbook.py`
- `tests/runbooks/all_features.md`
- `tests/runbooks/minimal.md`

**Estimated scope:** Medium

### Checkpoint 1: Foundation
- [x] `make test`, `make ty`, `make format` clean; CI green on `main`
- [x] Parser handles `tests/runbooks/all_features.md`

---

## Phase 2: Walking skeleton

## Task 4: Backend protocol, entry point loader, shell backend

**Description:** `backends/__init__.py` defines the `Backend` protocol and `load_backends(entry_points=None) -> dict[str, Backend]` keyed by language, raising a clear error naming both backends when two claim the same language. Settle the exact `run()` shape here (a generator of output lines that returns the exit code, or similar) and record it in the protocol docstring. `backends/shell.py` runs a block as one `bash` script with `set -eo pipefail` via `Popen`, stdout+stderr merged, stdin inherited, lines yielded as they arrive. `validate()` runs `bash -n`. Registered in `pyproject.toml`.

**Acceptance criteria:**
- [x] `load_backends()` returns the shell backend for `sh`, `bash` and `shell`
- [x] A failing command mid-block stops the block with that command's exit code; a failure inside a pipe is caught
- [x] Two fake backends claiming one language raise an error naming both

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_backend_loading.py tests/backends/test_shell.py`

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/backends/__init__.py`
- `paulrun/backends/shell.py`
- `pyproject.toml`
- `tests/test_backend_loading.py`
- `tests/backends/test_shell.py`

**Estimated scope:** Medium

## Task 5: Runner and `paulrun go` (shell blocks only)

**Description:** `runner.py` walks a `Runbook`'s steps and runs each `run` block through its backend, with the runbook's directory as `cwd`. It emits events (step started, block code, output line, block finished with exit code and duration, run finished) to a sink, so the CLI can print them and the transcript can later record them from the same stream. Block env sets `PYTHONUNBUFFERED=1`, `GIT_PAGER=cat`, `PAGER=cat`. `cli.py` adds `go RUNBOOK` printing events with rich (`console.out()` for code and output lines; `print(markup=False)` still converts `:emoji:` codes and wraps long lines). Stops on the first non-zero exit. Until Task 10's `validate()` exists, the runner refuses up front to start a runbook with a `run` block no backend handles.

**Acceptance criteria:**
- [x] Output from a slow block (e.g. `for i in 1 2 3; do echo $i; sleep 0.2; done`) appears line by line, not all at the end
- [x] Blocks run in the runbook's directory regardless of where `paulrun` is invoked
- [x] A failing block stops the run; later steps don't run

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py`
- [x] Manual check: run a two-step shell runbook from another directory and watch output stream

**Dependencies:** Tasks 3, 4

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_runner.py`
- `tests/test_cli.py`
- `tests/runbooks/two_steps.md`

**Estimated scope:** Medium

### Checkpoint 2: Walking skeleton
- [x] `paulrun go` on a two-step shell runbook streams output live and stops on failure
- [x] Review with Paul before widening (approved 2026-10-08)

---

## Phase 3: Core features

## Task 6: Inputs: declare, collect, validate, substitute, mask

**Description:** `inputs.py` holds the `Input` model, `PLACEHOLDER` regex, `collect(inputs, env, prompter)` (environment first, then prompt; hidden prompt for secrets; `pattern` full-match with re-prompt, or failure if the bad value came from the environment), `substitute(text, values)` for non-secret inputs only, and `mask(text, secrets)`. The runner exports every input to block env and substitutes non-secret placeholders into `run` block code. A `Prompter` protocol (with a Click-backed implementation in `cli.py`) makes prompts injectable for tests.

**Acceptance criteria:**
- [x] An input set in the environment is used without prompting; a pattern mismatch from the environment fails with a clear message
- [x] `<VERSION>` in a `run` block is substituted before execution; a secret is available as `$NAME` but never substituted
- [x] `mask()` replaces every occurrence of every secret value with `****`

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_inputs.py tests/test_runner.py`

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
- [x] `docstring` text is printed with inputs substituted
- [x] Answering `n` to a `confirm` stops the run, exits 1, and later steps don't run
- [x] Declining the start prompt runs nothing and exits 1

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py`

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
- [x] `go --dry` on a runbook whose blocks would create files creates nothing
- [x] Every `run` block is printed with non-secret inputs substituted
- [x] No prompt for secret inputs; non-secret inputs still collected

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py`

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
- [x] A Python block runs with `sys.executable` when no `python` key is set
- [x] With `python: <command>` set, blocks run under that command (tested with a stub interpreter script in `tmp_path`)
- [x] A Python block that raises exits non-zero and stops the run

**Verification:**
- [x] Tests pass: `uv run pytest tests/backends/test_python.py`

**Dependencies:** Task 5

**Files likely touched:**
- `paulrun/backends/python.py`
- `pyproject.toml`
- `tests/backends/test_python.py`

**Estimated scope:** Small

## Task 10: Validation and `paulrun check`

**Description:** `validate(runbook, backends) -> Report` collects errors and warnings with line numbers, and `go` calls it first. Errors: missing `title`; input missing `name` or `description`; input name not UPPER_SNAKE_CASE; invalid `pattern` regex; undeclared placeholder in a `run`/`docstring`/`confirm` block or `output_path`; secret used as a placeholder; `run` block with no backend; `run`/`docstring`/`confirm` block before the first `##`; `python` command not on `PATH`; backend `validate()` failures (`bash -n`, `compile()`). Warnings: unknown top-level keys, unknown input keys, declared-but-unused inputs, `shellcheck` findings when it's installed. `check RUNBOOK` prints the report and exits 1 on any error.

**Acceptance criteria:**
- [x] Each error case above has a broken fixture runbook and a test asserting the message and line number
- [x] `paulrun check` exits 0 on `tests/runbooks/all_features.md` and 1 on every broken fixture
- [x] `paulrun go` refuses to start on a runbook with errors

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_validate.py tests/test_cli.py`
- [x] Manual check: `uv run paulrun check tests/runbooks/all_features.md`

**Dependencies:** Tasks 6, 9

**Files likely touched:**
- `paulrun/validate.py`
- `paulrun/cli.py`
- `tests/test_validate.py`
- `tests/runbooks/broken/*.md`
- `tests/test_cli.py`

**Estimated scope:** Medium

### Checkpoint 3: Core features
- [x] `paulrun check` and `paulrun go --dry` work on `tests/runbooks/all_features.md`
- [x] All `check` error cases from the spec covered by fixture tests

---

## Phase 4: Remaining features

## Task 11: `--step`

**Description:** `go --step` asks `[y]es / [s]kip / [q]uit` after printing each `run` block's code. Skip moves on; quit ends the run as aborted (exit 1). Ignored with `--dry`. Skips are emitted as events so Task 12 can record them.

**Acceptance criteria:**
- [x] `y` runs the block, `s` skips it and the run continues, `q` aborts with exit 1
- [x] `--dry --step` behaves exactly like `--dry`

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py`

**Dependencies:** Task 10

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_runner.py`
- `tests/test_cli.py`

**Estimated scope:** Small

## Task 12: Transcript (`output_path`)

**Description:** `transcript.py` subscribes to runner events and appends the plain transcript format from the spec to `output_path`: run header with timestamp and masked inputs, `=== step ===` lines, the code indented four spaces, verbatim output, `exit N (Xs)`, confirm answers, `skipped (--step)`, and the `--- finished:` line for ok, failed and aborted. Path has placeholders substituted, is resolved relative to the runbook, and parent directories are created. All text is masked before writing. Not written under `--dry`.

**Acceptance criteria:**
- [x] Two runs append two complete transcripts to the same file
- [x] A secret value echoed by a block never appears in the file
- [x] Failed, aborted and skipped runs produce the right finish/skip lines; `--dry` writes nothing

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_transcript.py`

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
- [x] `paulrun inputs` works on a runbook whose body is deliberately malformed
- [x] `paulrun backends` lists shell and python with their languages
- [x] An injected external backend shows up in `backends` and runs its block via `go`

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_cli.py tests/test_backend_loading.py`

**Dependencies:** Task 10

**Files likely touched:**
- `paulrun/cli.py`
- `tests/test_cli.py`
- `tests/test_backend_loading.py`

**Estimated scope:** Small

### Checkpoint 4: Feature complete
- [x] Every code-level success criterion in the spec has a passing test
- [x] Review with Paul (approved 2026-10-12)

---

## Phase 5: Docs and dogfooding

## Task 14: mkdocs site

**Description:** `mkdocs.yml` mirroring clientele's material theme setup (light/dark palette toggle, code copy, search, nav tabs), `repo_url` to phalt/paulrun, default GitHub Pages URL. Pages: `index.md`, `install.md`, `runbook-format.md` (the full contract, written for humans, including the non-interactive and secret-masking caveats), `cli.md` (every command, flag and exit code).

**Acceptance criteria:**
- [x] `make docs-serve` renders every page with working nav
- [x] `runbook-format.md` covers every frontmatter key, fence type, placeholder rule and the transcript format
- [x] `uv run mkdocs build --strict` passes

**Verification:**
- [x] Build succeeds: `uv run mkdocs build --strict`
- [x] Manual check: Paul skims the rendered site (approved 2026-10-12)

**Dependencies:** Task 10

**Files likely touched:**
- `mkdocs.yml`
- `docs/index.md`
- `docs/install.md`
- `docs/runbook-format.md`
- `docs/cli.md`

**Estimated scope:** Medium

## Task 14b: `input` blocks (inputs asked for part way through a run)

Added 2026-10-12, after Checkpoint 4, as part of 0.1.0. A format change, approved by Paul.

**Description:** A ```` ```input ```` fence declares an input inside a step, using the same keys as a frontmatter input (`name`, `description`, optional `pattern` and `secret`) written as YAML. paulrun asks for it when the run reaches the block, rather than before the first step, for values that only exist part way through: a one-time 2FA code that expires in seconds, or something a manual step produces, like a PR number or release URL. It pairs with `confirm`: do this by hand, then tell me what you got.

````markdown
## Publish to npm

```input
name: OTP
description: The code from your authenticator app
pattern: '^\d{6}$'
secret: true
```

```sh run
npm publish --otp "$OTP"
```
````

Behaviour:
- **Collected like any input:** the environment first (an empty variable counts as unset), otherwise a prompt, hidden for secrets, with `pattern` re-asking for a typed value and failing for one from the environment.
- **From then on it's a normal input:** set in the environment of every later `run` block, substituted as `<NAME>` in later `run`, `docstring` and `confirm` blocks if it isn't secret, and masked as `****` everywhere if it is.
- **`--dry`:** not asked for, since the value may not exist yet. Later blocks show `<NAME>` as written. Frontmatter inputs are still collected under `--dry`, as now.
- **`--step`:** an `input` block is always asked; `--step` only applies to `run` blocks.
- **Transcript:** `input: NAME=value` where it was asked, or `input: NAME=****` for a secret.
- **Ctrl-C** at its prompt finishes the run as interrupted at that step, like a `confirm`.

`check` rules:
- The block must be valid YAML and a mapping, with the same rules and warnings as a frontmatter input.
- Its name can't be declared anywhere else, in the frontmatter or another `input` block.
- Using its placeholder before the block, or in `output_path`, is an error, since it hasn't been asked for yet. Using it as `$NAME` in a block before it is an error too.
- An `input` block before the first `##` is an error, like the other blocks.

`paulrun inputs` lists block inputs after the frontmatter ones, marked with the step that asks for them (e.g. `asked in "Publish to npm"`). It still works on a runbook whose body can't be read, listing only the frontmatter inputs; block inputs need the body.

**Acceptance criteria:**
- [x] An `input` block is asked for when the run reaches it, not before the first step, and its value reaches every later block, substituted or as `$NAME`
- [x] A secret `input` block's value never appears on screen or in the transcript
- [x] `check` errors on each new rule above, each with a broken fixture and its line number
- [x] `--dry` doesn't ask for `input` blocks; the transcript records each one
- [x] `paulrun inputs` lists block inputs with their step, and still works on `tests/runbooks/broken-body.md`
- [x] The spec's runbook format, `docs/runbook-format.md`, `docs/cli.md` and the 0.1.0 entry in `CHANGELOG.md` (and `docs/CHANGELOG.md`) describe `input` blocks

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runbook.py tests/test_validate.py tests/test_runner.py tests/test_transcript.py tests/test_cli.py`
- [x] Build succeeds: `uv run mkdocs build --strict`
- [x] Manual check: run `tests/runbooks/input-block-example.md` in a terminal, typing a secret at an `input` block part way through

**Dependencies:** Tasks 12, 13, 14

**Files likely touched:**
- `specs/SPEC.md`
- `paulrun/runbook.py` (the new block kind, its YAML and line numbers)
- `paulrun/validate.py`
- `paulrun/runner.py`
- `paulrun/transcript.py`
- `paulrun/cli.py`
- `tests/test_runbook.py`, `tests/test_validate.py`, `tests/test_runner.py`, `tests/test_transcript.py`, `tests/test_cli.py`
- `tests/runbooks/input-block-example.md`, `tests/runbooks/broken/*.md`
- `docs/runbook-format.md`, `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Medium

## Task 15: README, CONTRIBUTING, CHANGELOG and project docs

**Description:** README (what it is, install with `uv tool install paulrun`, a 30-second example, link to docs, macOS/Linux note). `CHANGELOG.md` and `docs/CHANGELOG.md` were written in Task 14 (0.1.0 entry, kept identical by `tests/test_docs.py`). `docs/backends.md` (protocol, built-ins, adding a backend to paulrun step by step, shipping an external one). `CONTRIBUTING.md` in clientele's shape, including the AI disclosure and the backend checklist. `SECURITY.md` and `CODE_OF_CONDUCT.md` copied from clientele with names swapped.

Decided with Paul (2026-10-13): the README example is a small `hello.md` that really runs, not the release example from `docs/index.md`. `Backend`, `Problem`, `stream`, `Interrupted` (`paulrun.backends`) and `PLACEHOLDER` (`paulrun.inputs`) are public API for external backends. Bugs in clientele's copies (clone command, `git branch -B`, unfinished sentences in the code of conduct) are fixed in paulrun's. `CONTRIBUTORS.md` added, as CONTRIBUTING asks for it. `readme = "README.md"` added to `pyproject.toml` so PyPI shows it.

**Acceptance criteria:**
- [x] README example runs as written (`tests/test_docs.py` runs each command and compares the output)
- [x] `CONTRIBUTING.md` and `docs/backends.md` walk through adding a backend to paulrun and shipping an external one (the example Node backend is tested end to end)
- [x] `mkdocs build --strict` still passes with the new pages in nav

**Verification:**
- [x] Build succeeds: `uv run mkdocs build --strict`
- [x] Manual check: Paul reads the README (approved 2026-10-13)

**Dependencies:** Tasks 13, 14, 14b

**Files likely touched:**
- `README.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `docs/backends.md`
- `docs/CHANGELOG.md`
- `SECURITY.md`, `CODE_OF_CONDUCT.md` (copied), `CONTRIBUTORS.md`
- `mkdocs.yml`, `pyproject.toml`, `tests/test_docs.py`

**Estimated scope:** Medium (mostly prose)

## Task 16: Examples and paulrun's own PUBLISHING.md

**Description:** `examples/hello.md` (smallest useful runbook: one input, a docstring, a shell block, a Python block), `examples/clientele-publishing.md` (the reworked clientele runbook with `output_path`), and `PUBLISHING.md` at the repo root for releasing paulrun itself (bump version, `make install`, commit, tag, push, confirm GitHub release, `make deploy-docs`, `make release`). A test runs `paulrun check` against every file in `examples/` and the root `PUBLISHING.md`.

Decided with Paul (2026-10-13), going with the recommendations:
- Both release runbooks start by checking the release can go ahead. The tree must be up to date and clean, apart from the changelogs and `logs/`. The tag must not exist yet, and `CHANGELOG.md` must have the version's section.
- They run `make test`, and print the version's changelog notes for the GitHub release.
- They clear `dist/` before `make release`, since `uv publish` uploads everything in it.
- They commit with `git commit -am`, not `git add .`, so a transcript in `logs/` is never committed. The commit is skipped when there's nothing to commit. That happens on paulrun's first release, since 0.1.0 and its changelog are already committed, and when rerunning a release.
- The GitHub release stays a `confirm` step. `examples/hello.md` is kept identical to the README's runbook by a test.

**Acceptance criteria:**
- [x] `paulrun check` passes on all examples and `PUBLISHING.md` (enforced by a test)
- [x] `paulrun go examples/hello.md` runs end to end
- [x] `paulrun go PUBLISHING.md --dry` shows a sensible release for a test version (tested on a copy, for both release runbooks)

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_examples.py`
- [ ] Manual check: `uv run paulrun go PUBLISHING.md --dry`

**Dependencies:** Task 15

**Files likely touched:**
- `examples/hello.md`
- `examples/clientele-publishing.md`
- `PUBLISHING.md`
- `tests/test_examples.py`
- `.gitignore` (`/logs/`, `examples/logs/`), `README.md` (link to the examples)

**Estimated scope:** Small

### Checkpoint 5: Ready to release (Paul only)
- [ ] Paul releases clientele with `paulrun go PUBLISHING.md`
- [ ] Paul releases paulrun 0.1.0 with its own PUBLISHING.md
- [ ] Docs deployed to `phalt.github.io/paulrun`
