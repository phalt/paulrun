# Implementation Plan: paulrun 0.2.0

Status: approved (2026-10-13)
Spec: [specs/SPEC-0.2.0.md](../specs/SPEC-0.2.0.md)
Tasks: [tasks/todo-0.2.0.md](todo-0.2.0.md)

## Overview

Build paulrun 0.2.0 as the spec describes. Runbooks can be kept in a runbook library (`~/runbooks`, or `$PAULRUN_LIBRARY`), and each book in it runs by name from anywhere. Blocks and transcripts go in the folder paulrun was started from. `paulrun library` lists the books, and `paulrun run` with no name picks one from the library. `run` replaces `go`, and is optional: `paulrun RUNBOOK` runs it. Inputs get `default` and `choices`.

The order is:

1. The breaking change first. Where blocks and transcripts go changes existing tests and documented output, so it's the riskiest part.
2. The runbook library, from name lookup to `paulrun library` to the picker.
3. The two input keys.
4. The new docs page.

Each task leaves `main` green and every documented example still running as written.

## Architecture decisions

- **The starting folder is read once, in `cli.py`.** `go` reads `Path.cwd()` and passes it down: `runner.run(..., cwd=...)` and `Transcript.for_runbook(runbook, cwd)`. Library modules never call `os.getcwd()`, so tests pass a folder in instead of changing directory. The backend protocol doesn't change. Backends already get `cwd`; only its value changes.
- **`PAULRUN_RUNBOOK_DIR` is set by the runner,** next to `_BLOCK_ENV`, as the runbook's resolved parent folder. It isn't an input, so validation still treats `<PAULRUN_RUNBOOK_DIR>` as undeclared.
- **One new module, `library.py`.** It has three functions:
  - `location(env) -> Path`: where the library is, `PAULRUN_LIBRARY` with `~` expanded, else `~/runbooks`.
  - `find(argument, cwd, folder) -> Path | None`: the spec's lookup rules.
  - `books(library) -> list[Book]`: frontmatter only, one `Book` per `*.md`, carrying any read error.

  Plain functions taking their inputs, so they're tested without touching the real home folder. `cli.py` connects them to Click.
- **Name lookup errors are Click usage errors** (exit 2), the same as 0.1.0's missing file. `RUNBOOK` changes from `click.Path(exists=True)` to a plain string, resolved through `library.find`.
- **`collect` applies defaults; the prompter only shows them.** If an answer is empty and the input has a default, `collect` uses the default. Choices are checked in `_matches` along with `pattern`. `ClickPrompter.ask` adds the default and choices to the prompt text. So the rules live in `inputs.py`, where `FakePrompter` tests reach them, and the Click layer only displays them.
- **`default` and `choices` go through the existing input path.** `parse_inputs`, `INPUT_KEYS` and `validate._inputs` already cover frontmatter inputs and `input` blocks together. Each new key is added once and works in both places.
- **Test isolation in `tests/conftest.py`.** Every test is started in its own temporary folder (Task 1), so a block or transcript a test causes can never land in the repo. `PAULRUN_LIBRARY` is pointed at an empty temporary folder (Task 4), so Paul's real library never affects a test.

## Dependency graph

```
blocks run in the starting folder + PAULRUN_RUNBOOK_DIR (1)
   │
   ├── transcripts relative to the starting folder (2)
   │      │
   │      └── `directory:` line in the overview (3)
   │
   └── name lookup for go / check / inputs (4)
          │
          └── `paulrun library` (5)
                 │
                 └── `run` replaces `go`, and is optional (5b)
                        │
                        └── picker for `paulrun run` (6)
                        │
                        └── runbook library docs page (9)   [also needs 3]

`default` on inputs (7) ── `choices` on inputs (8)          [independent of 1-6]
```

## Task list

Full task bodies (acceptance criteria, verification, files) are in [todo-0.2.0.md](todo-0.2.0.md).

### Phase 1: Where things run (the breaking change)
- [x] Task 1: Blocks run in the starting folder, with `PAULRUN_RUNBOOK_DIR`
- [x] Task 2: Transcripts relative to the starting folder
- [x] Task 3: `directory:` line in the run overview

### Checkpoint 1: Breaking change in
- [x] `make test`, `make ty`, `make format` clean, and `git status` shows nothing new after `make test`
- [x] `paulrun go PUBLISHING.md --dry` from the repo root looks the same as for 0.1.0, apart from the `directory:` line
- [x] Review with Paul before building on it (approved 2026-10-13)

### Phase 2: The runbook library
- [x] Task 4: Find books in the library by name for `go`, `check` and `inputs`
- [x] Task 5: `paulrun library`
- [x] Task 5b: `run` replaces `go`, and runbooks run with no command (added 2026-10-14)
- [ ] Task 6: Pick a book from the library for `paulrun run` with no runbook

### Checkpoint 2: Runbook library works
- [ ] With `PAULRUN_LIBRARY=tests/library`, `paulrun library`, `paulrun <name> --dry` and `paulrun run` (the picker) all work from another folder
- [ ] Paul tries his own `rebuild-frontend` book from his library in the work repo (Paul only)

### Phase 3: Input defaults and choices
- [ ] Task 7: `default` on inputs
- [ ] Task 8: `choices` on inputs

### Checkpoint 3: Feature complete
- [ ] Every code-level success criterion in the spec has a passing test
- [ ] Review with Paul

### Phase 4: Docs
- [ ] Task 9: "Your runbook library" docs page, README and home page

### Checkpoint 4: Ready to release (Paul only)
- [ ] `CHANGELOG.md`'s `## 0.2.0` section leads with the runbook library, then the breaking change, and covers every feature
- [ ] `uv run mkdocs build --strict` passes
- [ ] Paul releases paulrun 0.2.0 with an unchanged `PUBLISHING.md`, run as `paulrun PUBLISHING.md`
- [ ] Docs deployed to `phalt.github.io/paulrun`

Agents never publish to PyPI or deploy docs (SPEC.md Boundaries).

## Parallelisation

There are two independent tracks:

- Tasks 1-6: where blocks run, then the runbook library.
- Tasks 7-8: input defaults and choices.

Tasks 7 and 8 touch `inputs.py`, `runbook.py` and `validate.py`, which Tasks 1-6 barely touch. The overlap is the `inputs` command in `cli.py`, which Task 4 also changes. Run the two tracks in parallel only with that in mind; otherwise build in order. Task 9 waits for 1-6.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Once blocks and transcripts go in the starting folder, a test run from the repo root writes into the repo, e.g. a `logs/` folder or files a test block creates | High | Task 1 adds an autouse fixture that starts every test in its own empty temporary folder. Checkpoint 1 checks `git status` after `make test` |
| Existing tests and fixtures rely on blocks running in the runbook's folder: `test_run_runs_blocks_in_the_runbook_directory`, `test_go_runs_blocks_in_the_runbook_directory`, and the `transcript_runbook` and `input_block_runbook` fixtures, which read `<runbook>.parent / "logs"` | Medium | Tasks 1 and 2 rewrite them for the new rule rather than deleting them (spec Testing strategy). Keep the test names honest, e.g. `..._in_the_starting_directory` |
| The `directory:` line is machine-specific, but `test_the_readme_example_runs_as_written` compares output exactly | Medium | Task 3 normalises the directory in that test, the way `without_durations` normalises times. The README shows a representative path |
| Fixtures with `python: uv run python` (`python-example.md`, the docs frontmatter example) run from a temporary folder once tests start there, so `uv` finds no project and may pick a different interpreter or be slow | Medium | Task 1 checks those tests still pass and stay fast. If they don't, those tests start in the repo root, or set `UV_PROJECT`, and the reason is written in the test. Checked in Task 1: only `examples/clientele-publishing.md` sets it, and its tests only `check` it and run it under `--dry`, so nothing runs `uv run python` from a temporary folder |
| Paul's real library at `~/runbooks` changes test results once it exists | Medium | Task 4's autouse fixture points `PAULRUN_LIBRARY` at an empty temporary folder for every test |
| A bare name matches a file in the starting folder (e.g. a `deploy` script) and shadows the `deploy` book in the library | Low | The spec decides this: paths win. Documented in `docs/cli.md`, and the run overview's title shows which runbook was picked |
| YAML types `default: 1.10` as a float and `default: yes` as a bool | Low | `check` errors on a non-string default and says to quote it (Task 7) |
| A misspelt command (`paulrun chekc deploy`) is read as a runbook called `chekc` | Low | It ends in the not-found usage error, which names `chekc`, so the typo shows. Click's "did you mean" for commands is lost; accepted as the price of an optional `run` |
| Removing `go` breaks anything that types it: muscle memory, notes, the 0.1.0 release transcripts | Medium | Paul chose a clean break over an alias (2026-10-14). The CHANGELOG's Breaking line says so, and `paulrun go x` gives a clear not-found error rather than doing something else |
| External backends now get the starting folder as `cwd` instead of the runbook's folder | Low | The protocol signature doesn't change. The CHANGELOG's breaking-change line covers backends too |

## Open questions

None. The spec settles the format and CLI. The two calls made here, that `collect` applies defaults and that tests start in a temporary folder, are implementation details. Both are listed above for review.
