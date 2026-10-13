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
- [ ] Started in folder A with the runbook in folder B, `output_path: logs/release-<VERSION>.md` writes `A/logs/release-1.2.0.md`, and nothing appears in B
- [ ] An absolute `output_path` is written where it says, wherever paulrun is started
- [ ] The `transcript:` line `go` prints at the end shows the new path

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_transcript.py tests/test_cli.py`
- [ ] Manual check: `uv run paulrun go PUBLISHING.md --dry` from the repo root still names `logs/release-<version>.md` in the header prose and writes nothing

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
- [ ] `paulrun go` and `paulrun go --dry` print `directory: <starting folder>` straight after the title
- [ ] The README example still runs exactly as written, apart from the normalised directory and durations
- [ ] Every documented `go` output in `README.md`, `docs/index.md` and `docs/cli.md` includes the line

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_runner.py tests/test_cli.py tests/test_docs.py tests/test_examples.py`
- [ ] Build succeeds: `uv run mkdocs build --strict`

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/runner.py`
- `paulrun/cli.py`
- `tests/test_runner.py`, `tests/test_cli.py`, `tests/test_docs.py`
- `README.md`, `docs/index.md`, `docs/cli.md`

**Estimated scope:** Medium (mostly docs)

### Checkpoint 1: Breaking change in
- [ ] `make test`, `make ty`, `make format` clean, and `git status` shows nothing new after `make test`
- [ ] `paulrun go PUBLISHING.md --dry` from the repo root looks the same as for 0.1.0, apart from the `directory:` line
- [ ] Review with Paul before building on it

---

## Phase 2: The runbooks folder

## Task 4: Find runbooks by name for `go`, `check` and `inputs`

**Description:** A new `paulrun/books.py` has `folder(env)` and `find(argument, cwd, folder)`.
- `folder(env)` is `PAULRUN_RUNBOOKS`, when it's set and not empty, with `~` expanded. Otherwise it's `~/runbooks`.
- `find` follows the spec's Decision 5:
  - a file that exists wins
  - otherwise an argument with no `/` is looked up as `<name>.md` in the folder, with a trailing `.md` allowed
  - anything else is not found
- `go`, `check` and `inputs` take `RUNBOOK` as a plain string and resolve it with `find`. Not found is a usage error (exit 2) naming both places looked in.
- Add `tests/books/` as a fixture runbooks folder, and an autouse conftest fixture that points `PAULRUN_RUNBOOKS` at an empty temporary folder for every test.
- Document name lookup and `PAULRUN_RUNBOOKS` in `docs/cli.md`.

**Acceptance criteria:**
- [ ] With `PAULRUN_RUNBOOKS` set, `go`, `check` and `inputs` all find `<folder>/<name>.md`, with or without the `.md`; without it, or with it empty, the folder is `~/runbooks` (tested with `HOME` pointed at a temporary folder)
- [ ] An existing file is used before a folder runbook of the same name, and an argument containing `/` is never looked up in the folder
- [ ] A name that isn't found exits 2 with `no runbook '<name>': no such file here, and no <name>.md in <folder>`

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_books.py tests/test_cli.py`
- [ ] Manual check: from `/tmp`, `PAULRUN_RUNBOOKS=~/Projects/paulrun/tests/books uv run --project ~/Projects/paulrun paulrun check <name>`

**Dependencies:** Task 1

**Files likely touched:**
- `paulrun/books.py`
- `paulrun/cli.py`
- `tests/conftest.py`
- `tests/test_books.py`, `tests/test_cli.py`
- `tests/books/*.md`
- `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Medium

## Task 5: `paulrun books`

**Description:** `books.books(folder)` reads each `*.md` directly inside the folder, frontmatter only, into a `Book` in name order: name, path, title, description, or the error that stopped its frontmatter being read. `paulrun books` prints the folder, then each entry in the layout the spec gives, aligned like `paulrun inputs`. An empty or missing folder prints `no runbooks in <folder>` with a hint about `PAULRUN_RUNBOOKS`, and exits 0. Add a `paulrun books` section to `docs/cli.md`.

**Acceptance criteria:**
- [ ] Lists each runbook's name and title, with its description underneath when it has one, in name order; a runbook with no title shows its name alone
- [ ] A runbook with unreadable frontmatter is still listed, with the reason; a runbook with a broken body is listed normally; subfolders and non-`.md` files are ignored
- [ ] An empty or missing folder says so and exits 0

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_books.py tests/test_cli.py`
- [ ] Manual check: `PAULRUN_RUNBOOKS=tests/books uv run paulrun books`

**Dependencies:** Task 4

**Files likely touched:**
- `paulrun/books.py`
- `paulrun/cli.py`
- `tests/test_books.py`, `tests/test_cli.py`
- `tests/books/*` (a broken-frontmatter runbook, a subfolder, a non-`.md` file)
- `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Small

## Task 6: Picker for `paulrun go` with no runbook

**Description:** `RUNBOOK` becomes optional for `go`.
- With none given, `go` lists the folder's runbooks numbered, `  1. <name>  <title>`, and asks `Run which?`.
- A listed number carries on exactly like `paulrun go <name>`, with `--dry` and `--step` applied.
- Anything else is asked again.
- A blank answer or Ctrl-C runs nothing, writes no transcript and exits 1.
- An empty folder is an error, exit 1, naming the folder.
- `check` and `inputs` still need a `RUNBOOK`.
- Document the picker in `docs/cli.md`.

**Acceptance criteria:**
- [ ] Picking a number runs that runbook, including under `--dry` and `--step`
- [ ] An answer that isn't a listed number is asked again; a blank answer or Ctrl-C exits 1, runs nothing and writes no transcript
- [ ] `paulrun go` with an empty runbooks folder exits 1 naming the folder

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_cli.py`
- [ ] Manual check: `PAULRUN_RUNBOOKS=tests/books uv run paulrun go --dry`, then pick one

**Dependencies:** Task 5

**Files likely touched:**
- `paulrun/cli.py`
- `tests/test_cli.py`
- `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Small

### Checkpoint 2: Runbooks folder works
- [ ] With `PAULRUN_RUNBOOKS=tests/books`, `paulrun books`, `paulrun go <name> --dry` and `paulrun go` (the picker) all work from another folder
- [ ] Paul tries his own `~/runbooks/rebuild-frontend.md` in the work repo (Paul only)

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
- [ ] Pressing enter at a prompt with a default uses the default; an environment value overrides it; the same works in an `input` block
- [ ] `check` reports each of the three errors on its line, with a broken fixture each
- [ ] `paulrun inputs` shows the default

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_inputs.py tests/test_runbook.py tests/test_validate.py tests/test_cli.py`
- [ ] Manual check: `uv run paulrun go tests/runbooks/default-example.md`, pressing enter at the prompt

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
- [ ] A typed answer outside `choices` is asked again, and an environment value outside them fails before anything runs, in frontmatter inputs and `input` blocks
- [ ] `check` reports each of the four errors on its line, with a broken fixture each
- [ ] `paulrun inputs` shows the choices, and the prompt lists them

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_inputs.py tests/test_runbook.py tests/test_validate.py tests/test_cli.py`
- [ ] Manual check: `uv run paulrun go tests/runbooks/choices-example.md`, typing a wrong answer first

**Dependencies:** Task 7

**Files likely touched:**
- `paulrun/inputs.py`, `paulrun/runbook.py`, `paulrun/validate.py`, `paulrun/cli.py`
- `tests/test_inputs.py`, `tests/test_runbook.py`, `tests/test_validate.py`, `tests/test_cli.py`
- `tests/runbooks/choices-example.md`, `tests/runbooks/broken/choices-*.md`
- `docs/runbook-format.md`, `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Medium (small changes across four modules)

### Checkpoint 3: Feature complete
- [ ] Every code-level success criterion in the spec has a passing test
- [ ] Review with Paul

---

## Phase 4: Docs

## Task 9: "Your runbooks folder" docs page, README and home page

**Description:** A new page, `docs/runbooks-folder.md` ("📚 Your runbooks folder"), added to the mkdocs nav under Documentation. It covers:
- the folder and `PAULRUN_RUNBOOKS`
- running by name, with paths winning over names
- `paulrun books` and the picker
- why blocks and transcripts go where you are
- `PAULRUN_RUNBOOK_DIR`

It includes a worked example: a runbook that clean-installs a frontend's dependencies under nvm, then rebuilds it, with generic paths and commands. The example:
- runs `source "$NVM_DIR/nvm.sh"` to load a shell function that's normally in your profile
- explains that a block's `cd` and `PATH` changes only last for that block
- uses a `choices` input for the frontend set to rebuild

The README and `docs/index.md` get a short "Your own runbooks" section, and `paulrun books` goes in the feature list. `tests/test_docs.py` checks that the worked example passes `paulrun check`.

**Acceptance criteria:**
- [ ] `docs/runbooks-folder.md` covers everything listed above and is in the nav
- [ ] The worked example passes `check` (tested), using `choices` and `source "$NVM_DIR/nvm.sh"`
- [ ] The README and home page mention the runbooks folder and `paulrun books`, and the README example test still passes

**Verification:**
- [ ] Tests pass: `uv run pytest tests/test_docs.py`
- [ ] Build succeeds: `uv run mkdocs build --strict`
- [ ] Manual check: Paul reads the new page in `make docs-serve`

**Dependencies:** Tasks 3, 6, 8

**Files likely touched:**
- `docs/runbooks-folder.md`
- `mkdocs.yml`
- `README.md`, `docs/index.md`
- `tests/test_docs.py`

**Estimated scope:** Medium (mostly prose)

### Checkpoint 4: Ready to release (Paul only)
- [ ] `CHANGELOG.md`'s `## 0.2.0` section leads with the breaking change and covers every feature
- [ ] `uv run mkdocs build --strict` passes
- [ ] Paul releases paulrun 0.2.0 with an unchanged `paulrun go PUBLISHING.md`
- [ ] Docs deployed to `phalt.github.io/paulrun`
