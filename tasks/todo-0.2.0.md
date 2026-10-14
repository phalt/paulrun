# paulrun 0.2.0 tasks

Plan: [tasks/plan-0.2.0.md](plan-0.2.0.md). Spec: [specs/SPEC-0.2.0.md](../specs/SPEC-0.2.0.md).

Every task also clears the standing bar:
- `make format`, `make ty` and `make test` are clean
- the `## 0.2.0` section of `CHANGELOG.md`, copied to `docs/CHANGELOG.md`, covers anything user-visible
- `docs/runbook-format.md` and `docs/cli.md` are updated in the same change as the behaviour they describe
- each new feature has a readable example in `tests/runbooks/`, used by the CLI tests

---

## Phase 1: Where things run (the breaking change)

## Task 1: Blocks run in the starting folder, with `PAULRUN_RUNBOOK_DIR`

**Description:** Blocks run in the folder paulrun was started from, not the runbook file's folder. This replaces 0.1.0 Decision 2.
- `runner.run` gets a `cwd` argument and passes it to every backend. `go` passes `Path.cwd()`.
- Every block's environment gets `PAULRUN_RUNBOOK_DIR`, the runbook's resolved parent folder.
- Add an autouse fixture to `tests/conftest.py` that starts every test in its own empty temporary folder, so nothing a test runs can write into the repo.
- Rewrite the existing tests for the old rule, `test_run_runs_blocks_in_the_runbook_directory` and `test_go_runs_blocks_in_the_runbook_directory`, for the new rule.
- Add a "Where blocks run" section to `docs/runbook-format.md`.
- Start the CHANGELOG's `## 0.2.0` section with the breaking change.

**Acceptance criteria:**
- [x] With the runbook in one folder and paulrun started in another, shell and Python blocks both run in the starting folder
- [x] `$PAULRUN_RUNBOOK_DIR` in a block is the runbook file's absolute folder, even when the runbook was given as a relative path; `<PAULRUN_RUNBOOK_DIR>` is still an undeclared-placeholder error
- [x] `git status` shows nothing new after `make test`

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py tests/test_validate.py`
- [x] Manual check: from `/tmp`, `uv run --project ~/Projects/paulrun paulrun go ~/Projects/paulrun/tests/runbooks/two_steps.md` runs its blocks in `/tmp`

**Dependencies:** None

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/conftest.py`
- `tests/test_runner.py`, `tests/test_cli.py`
- `docs/runbook-format.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Medium

## Task 2: Transcripts relative to the starting folder

**Description:** A relative `output_path` is resolved from the starting folder, not the runbook's folder. An absolute one is kept as it is.
- `transcript_path` and `Transcript.for_runbook` take the folder, and `go` passes `Path.cwd()`.
- Update the `transcript_runbook` and `input_block_runbook` fixtures, and the tests that read `<runbook>.parent / "logs"`, to look in the starting folder.
- Update the Transcript section of `docs/runbook-format.md`, and add the change to the CHANGELOG's breaking-change line.

**Acceptance criteria:**
- [x] Started in folder A with the runbook in folder B, `output_path: logs/release-<VERSION>.md` writes `A/logs/release-1.2.0.md`, and nothing appears in B
- [x] An absolute `output_path` is written where it says, wherever paulrun is started
- [x] The `transcript:` line `go` prints at the end shows the new path

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_transcript.py tests/test_cli.py`
- [x] Manual check: `uv run paulrun go PUBLISHING.md --dry` from the repo root still names `logs/release-<version>.md` in the header prose and writes nothing

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/transcript.py`
- `paulrun/cli.py`
- `tests/test_transcript.py`, `tests/test_cli.py`
- `docs/runbook-format.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Small

## Task 3: `directory:` line in the run overview

**Description:** The overview shows the folder blocks will run in, on a `directory: <path>` line after the title, under `--dry` too. This shows where something like `rm -rf node_modules` will run before you answer `Start?`.
- `runner.Overview` gets a `directory` field, and `_print_event` prints it.
- Update every documented `go` output to include the line: `README.md`, `docs/index.md` and `docs/cli.md`.
- `test_the_readme_example_runs_as_written` normalises the directory, the way it already normalises durations.

**Acceptance criteria:**
- [x] `paulrun go` and `paulrun go --dry` print `directory: <starting folder>` straight after the title
- [x] The README example still runs exactly as written, apart from the normalised directory and durations
- [x] Every documented `go` output in `README.md`, `docs/index.md` and `docs/cli.md` includes the line

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py tests/test_docs.py tests/test_examples.py`
- [x] Build succeeds: `uv run mkdocs build --strict`

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_runner.py`, `tests/test_cli.py`, `tests/test_docs.py`
- `README.md`, `docs/index.md`, `docs/cli.md`

**Estimated scope:** Medium (mostly docs)

### Checkpoint 1: Breaking change in
- [x] `make test`, `make ty`, `make format` clean, and `git status` shows nothing new after `make test`
- [x] `paulrun go PUBLISHING.md --dry` from the repo root looks the same as for 0.1.0, apart from the `directory:` line
- [x] Review with Paul before building on it (approved 2026-10-13)

---

## Phase 2: The runbook library

## Task 4: Find books in the library by name for `go`, `check` and `inputs`

**Description:** A new `paulrun/library.py` has `location(env)` and `find(argument, cwd, library)`.
- `location(env)` is where the library is: `PAULRUN_LIBRARY`, when it's set and not empty, with `~` expanded. Otherwise it's `~/runbooks`.
- `find` follows the spec's Decision 5:
  - a file that exists wins
  - otherwise an argument with no `/` is looked up as the book `<name>.md` in the library, with a trailing `.md` allowed
  - anything else is not found
- `go`, `check` and `inputs` take `RUNBOOK` as a plain string and resolve it with `find`. Not found is a usage error (exit 2) naming both places looked in.
- Add `tests/library/` as a fixture library, and an autouse conftest fixture that points `PAULRUN_LIBRARY` at an empty temporary folder for every test.
- Document name lookup and `PAULRUN_LIBRARY` in `docs/cli.md`.

**Acceptance criteria:**
- [x] With `PAULRUN_LIBRARY` set, `go`, `check` and `inputs` all find the book `<library>/<name>.md`, with or without the `.md`; without it, or with it empty, the library is `~/runbooks` (tested with `HOME` pointed at a temporary folder)
- [x] An existing file is used before a book of the same name, and an argument containing `/` is never looked up in the library
- [x] A name that isn't found exits 2 with `no runbook '<name>': no such file here, and no <name>.md in the library at <library>`

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_library.py tests/test_cli.py`
- [x] Manual check: from `/tmp`, `PAULRUN_LIBRARY=~/Projects/paulrun/tests/library uv run --project ~/Projects/paulrun paulrun check <name>`

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/library.py`
- `paulrun/cli.py`
- `tests/conftest.py`
- `tests/test_library.py`, `tests/test_cli.py`
- `tests/library/*.md`
- `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Medium

## Task 5: `paulrun library`

**Description:** `library.books(library)` reads each `*.md` directly inside the library, frontmatter only, into a `Book` in name order: name, path, title, description, or the error that stopped its frontmatter being read. `paulrun library` prints `library: <where it is>`, then each book in the layout the spec gives, aligned like `paulrun inputs`. An empty or missing library prints `no books in the library at <library>` with a hint about `PAULRUN_LIBRARY`, and exits 0. Add a `paulrun library` section to `docs/cli.md`.

**Acceptance criteria:**
- [x] Lists each book's name and title, with its description underneath when it has one, in name order; a book with no title shows its name alone
- [x] A book with unreadable frontmatter is still listed, with the reason; a book with a broken body is listed normally; subfolders and non-`.md` files are ignored
- [x] An empty or missing library says so and exits 0

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_library.py tests/test_cli.py`
- [x] Manual check: `PAULRUN_LIBRARY=tests/library uv run paulrun library`

**Dependencies:** Task 4

**Files likely touched:**
- `paulrun/library.py`
- `paulrun/cli.py`
- `tests/test_library.py`, `tests/test_cli.py`
- `tests/library/*` stays a clean example library that passes `check`. The broken-frontmatter book, subfolder and non-`.md` file are made in `tmp_path` by the CLI tests instead
- `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Small

## Task 5b: `run` replaces `go`, and runbooks run with no command

Added 2026-10-14, after Task 5, as part of 0.2.0. A CLI change, approved by Paul (spec Decisions 6 and 7).

**Description:** `paulrun run RUNBOOK` replaces `paulrun go RUNBOOK`, and `paulrun RUNBOOK` does the same with no command at all.
- Rename the `go` command to `run`. `go` is removed, with no alias.
- The `paulrun` group takes a runbook in place of a command. When the first argument isn't a command name, `--help` or `--version`, it's run as if `run` came first, so options work on either side: `paulrun deploy --dry` and `paulrun --dry deploy`.
- Bare `paulrun` still shows help. Usage reads `paulrun [OPTIONS] RUNBOOK | COMMAND [ARGS]...`.
- Command names win: `paulrun check` is always the command. `paulrun library` marks a book whose name is a command, with how to run it (`paulrun run check`).
- Change every `paulrun go` to `paulrun RUNBOOK` (or `paulrun run` where it reads better) in the code, tests, fixture runbooks, examples, `PUBLISHING.md`, README, docs and CONTRIBUTING. The 0.1.0 files (`specs/SPEC.md`, `tasks/plan.md`, `tasks/todo.md`) and the 0.1.0 CHANGELOG entry stay as they were, since they record 0.1.0.
- CHANGELOG: a **Breaking** line saying `go` is now `run`, and that `paulrun RUNBOOK` works on its own.

**Acceptance criteria:**
- [x] `paulrun RUNBOOK` and `paulrun run RUNBOOK` give the same output and exit code, for a file and for a book, with `--dry` and `--step` before or after the runbook
- [x] `paulrun go ...` is a usage error (it's read as a runbook called `go`, which doesn't exist); bare `paulrun` and `paulrun --help` show help listing `run`; `paulrun --version` still works
- [x] A command name is never read as a runbook, and `paulrun library` marks a book that shares a command's name
- [x] No `paulrun go` is left in the code, tests, fixtures, examples, `PUBLISHING.md`, README, docs or CONTRIBUTING, apart from the 0.1.0 CHANGELOG entry

**Verification:**
- [x] Tests pass: `make test`
- [x] Build succeeds: `uv run mkdocs build --strict`
- [x] Manual check: `VERSION=9.9.9 uv run paulrun PUBLISHING.md --dry` from the repo root, and `PAULRUN_LIBRARY=tests/library uv run paulrun say-where` from `/tmp`

**Dependencies:** Task 5

**Files likely touched:**
- `paulrun/cli.py`
- `tests/test_cli.py`, `tests/test_docs.py`, `tests/test_examples.py`, `tests/test_interrupt.py`
- `tests/runbooks/*.md`, `tests/library/*.md`, `examples/*.md`, `PUBLISHING.md`
- `README.md`, `CONTRIBUTING.md`, `docs/cli.md`, `docs/index.md`, `docs/runbook-format.md`, `docs/backends.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Large in files, small in code. Almost every file is a mechanical `paulrun go` rename; the only new logic is the group taking a runbook in place of a command.

## Task 6: Pick a book from the library for `paulrun run` with no runbook

**Description:** `RUNBOOK` becomes optional for `run`.
- With none given, `run` lists the library's books numbered, `  1. <name>  <title>`, and asks `Run which?`.
- A listed number carries on exactly like `paulrun run <name>`, with `--dry` and `--step` applied.
- Bare `paulrun`, with no command, still shows help (spec Decision 6).
- Anything else is asked again.
- A blank answer or Ctrl-C runs nothing, writes no transcript and exits 1.
- An empty library is an error, exit 1, saying where the library is.
- `check` and `inputs` still need a `RUNBOOK`.
- Document the picker in `docs/cli.md`.

**Acceptance criteria:**
- [x] Picking a number runs that book, including under `--dry` and `--step`
- [x] An answer that isn't a listed number is asked again; a blank answer or Ctrl-C exits 1, runs nothing and writes no transcript
- [x] `paulrun run` with an empty library exits 1, saying where the library is

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_cli.py`
- [x] Manual check: `PAULRUN_LIBRARY=tests/library uv run paulrun run --dry`, then pick a book

**Dependencies:** Task 5b

**Files likely touched:**
- `paulrun/cli.py`
- `tests/test_cli.py`
- `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Small

### Checkpoint 2: Runbook library works
- [x] With `PAULRUN_LIBRARY=tests/library`, `paulrun library`, `paulrun <name> --dry` and `paulrun run` (the picker) all work from another folder
- [x] Paul tries his own `rebuild-frontend` book from his library in the work repo (Paul only; approved 2026-10-14)

---

## Phase 3: Input defaults and choices

## Task 7: `default` on inputs

**Description:** Inputs, in frontmatter and in `input` blocks, take an optional `default`.
- `Input` gets `default: str | None`, and `parse_inputs` reads it when it's a string.
- `collect`: the environment still comes first. An empty answer at the prompt takes the default, and is still checked against `pattern`.
- `ClickPrompter.ask` shows the default in the prompt.
- `INPUT_KEYS` gains `default`, so it's no longer an unknown-key warning.
- `check` errors:
  - a default that isn't a string, with a message saying to quote it
  - a default on a secret
  - a default that doesn't match the input's `pattern`
- `paulrun inputs` shows a `default: <value>` line.
- Add a readable `tests/runbooks/default-example.md`, a broken fixture per error, and the Inputs docs in `docs/runbook-format.md`.

**Acceptance criteria:**
- [x] Pressing enter at a prompt with a default uses the default; an environment value overrides it; the same works in an `input` block
- [x] `check` reports each of the three errors on its line, with a broken fixture each
- [x] `paulrun inputs` shows the default

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_inputs.py tests/test_runbook.py tests/test_validate.py tests/test_cli.py`
- [x] Manual check: `uv run paulrun tests/runbooks/default-example.md`, pressing enter at the prompt

**Dependencies:** None (independent of Tasks 1-6)

**Files likely touched:**
- `paulrun/inputs.py`, `paulrun/runbook.py`, `paulrun/validate.py`, `paulrun/cli.py`
- `tests/test_inputs.py`, `tests/test_runbook.py`, `tests/test_validate.py`, `tests/test_cli.py`
- `tests/runbooks/default-example.md`, `tests/runbooks/broken/default-*.md`
- `docs/runbook-format.md`, `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Medium (small changes across four modules)

## Task 8: `choices` on inputs

**Description:** Inputs, in frontmatter and in `input` blocks, take an optional `choices` list.
- `Input` gets `choices: tuple[str, ...]`, and `parse_inputs` reads it when it's a list of strings.
- `collect` checks choices along with `pattern`. A typed answer that isn't one of them is asked again with `<NAME> must be one of: a, b, c`. A value from the environment that isn't one fails before anything runs.
- `ClickPrompter.ask` lists the choices in the prompt.
- `INPUT_KEYS` gains `choices`.
- `check` errors:
  - `choices` isn't a non-empty list of strings
  - `choices` on a secret
  - a choice that doesn't match the input's `pattern`
  - a `default` that isn't one of the `choices`
- `paulrun inputs` shows a `choices: a, b, c` line.
- Add a readable `tests/runbooks/choices-example.md`, a broken fixture per error, and the docs.

**Acceptance criteria:**
- [x] A typed answer outside `choices` is asked again, and an environment value outside them fails before anything runs, in frontmatter inputs and `input` blocks
- [x] `check` reports each of the four errors on its line, with a broken fixture each
- [x] `paulrun inputs` shows the choices, and the prompt lists them

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_inputs.py tests/test_runbook.py tests/test_validate.py tests/test_cli.py`
- [x] Manual check: `uv run paulrun tests/runbooks/choices-example.md`, typing a wrong answer first

**Dependencies:** Task 7

**Files likely touched:**
- `paulrun/inputs.py`, `paulrun/runbook.py`, `paulrun/validate.py`, `paulrun/cli.py`
- `tests/test_inputs.py`, `tests/test_runbook.py`, `tests/test_validate.py`, `tests/test_cli.py`
- `tests/runbooks/choices-example.md`, `tests/runbooks/broken/choices-*.md`
- `docs/runbook-format.md`, `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Medium (small changes across four modules)

### Checkpoint 3: Feature complete
- [x] Every code-level success criterion in the spec has a passing test
- [x] Review with Paul (approved 2026-10-14)

---

## Phase 4: Docs

## Task 9: "Your runbook library" docs page, README and home page

**Description:** A new page, `docs/library.md` ("📚 Your runbook library"), added to the mkdocs nav under Documentation. It talks about the library and its books throughout, and covers:
- the library, where it is, and `PAULRUN_LIBRARY`
- running a book by name, with paths winning over names
- `paulrun library` and the picker
- why blocks and transcripts go where you are
- `PAULRUN_RUNBOOK_DIR`

It includes a worked example: a runbook that clean-installs a frontend's dependencies under nvm, then rebuilds it, with generic paths and commands. The example:
- runs `source "$NVM_DIR/nvm.sh"` to load a shell function that's normally in your profile
- explains that a block's `cd` and `PATH` changes only last for that block
- uses a `choices` input for the frontend set to rebuild

The README and `docs/index.md` get a short "Your runbook library" section, and the library goes in the feature list. `tests/test_docs.py` checks that the worked example passes `paulrun check`.

**Acceptance criteria:**
- [ ] `docs/library.md` covers everything listed above and is in the nav
- [ ] The worked example passes `check` (tested), using `choices` and `source "$NVM_DIR/nvm.sh"`
- [ ] The README and home page mention the runbook library and `paulrun library`, and the README example test still passes

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_docs.py`
- [ ] Build succeeds: `uv run mkdocs build --strict`
- [ ] Manual check: Paul reads the new page in `make docs-serve`

**Dependencies:** Tasks 3, 6, 8

**Files likely touched:**
- `docs/library.md`
- `mkdocs.yml`
- `README.md`, `docs/index.md`
- `tests/test_docs.py`

**Estimated scope:** Medium (mostly prose)

### Checkpoint 4: Ready to release (Paul only)
- [ ] `CHANGELOG.md`'s `## 0.2.0` section leads with the runbook library, then the breaking change, and covers every feature
- [ ] `uv run mkdocs build --strict` passes
- [ ] Paul releases paulrun 0.2.0 with an unchanged `PUBLISHING.md`, run as `paulrun PUBLISHING.md`
- [ ] Docs deployed to `phalt.github.io/paulrun`
