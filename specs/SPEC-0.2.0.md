# Spec: paulrun 0.2.0

Status: approved (2026-10-13)
Version target: 0.2.0

This builds on [SPEC.md](SPEC.md), the 0.1.0 spec. Anything not mentioned here is unchanged.

## Objective

paulrun becomes Paul's personal procedure runner. His runbooks are kept in a **runbook library**, one folder of books (markdown runbooks). Each book runs by name from anywhere, in the folder paulrun was started from.

**User:** Paul, for procedures in repos he doesn't own (rebuilding a work project's frontend) and ones he repeats across projects (updating a project's dependencies). Still published for anyone who wants it.

**Why:** 0.1.0 proved the release use case, where the runbook lives in the repo it releases. The next procedures Paul forgets don't belong in the repo they run against: a work repo isn't the place for his own notes, and a generic runbook is useful in many projects. 0.1.0 can't run a runbook against any folder but its own.

### User stories

- As Paul, I keep `rebuild-frontend.md` in my library at `~/runbooks`, `cd` into the work repo, run `paulrun rebuild-frontend`, and the frontend is rebuilt there.
- As Paul, I run `paulrun update-project-deps` in three different projects, and each run works on the project I'm in.
- As Paul, I run `paulrun library` to see which books are in my library and what each one does.
- As Paul, I run `paulrun run` with no name, pick a book from a numbered list of my library, and it runs.
- As Paul, I give an input a `default` and press enter instead of typing the usual value.
- As Paul, I give an input `choices`, and paulrun only accepts one of them.
- As Paul, I still release paulrun from the repo root with `PUBLISHING.md` unchanged, now as `paulrun PUBLISHING.md`.
- As Paul, I type `paulrun <runbook>` and it runs, the way I'd type the name of any script; `paulrun run <runbook>` says the same thing in full.

## Decisions

1. **Blocks run in the folder paulrun was started from.** This applies to every runbook, a local file or a book from the library. It replaces 0.1.0 Decision 2, which ran blocks in the runbook file's folder.
2. **A relative `output_path` is resolved from the folder paulrun was started from as well.** Started in `/test/foo`, `output_path: logs/output.md` writes `/test/foo/logs/output.md`. Absolute paths are kept as they are.
3. **The runbook library** is the folder `~/runbooks`, or `$PAULRUN_LIBRARY` when it's set and not empty. `~` in the variable's value is expanded. There's no config file, and there's only one library.
4. **The library is flat.** Every `*.md` file directly inside it is a book, and its name is the file name without `.md`. Subfolders and other files are ignored, so `~/runbooks/logs/` is a safe place for transcripts.
5. **Paths win over names.** If the argument is a file that exists, that file is the runbook, as in 0.1.0. Otherwise, if it has no `/`, it's looked up in the library as `<name>.md`. A trailing `.md` is allowed, so `rebuild-frontend` and `rebuild-frontend.md` find the same runbook. An argument containing `/` is only ever a path.
6. **`run` replaces `go`, and is optional.** `paulrun run RUNBOOK` runs a runbook, and so does `paulrun RUNBOOK`: anything that isn't a command name is taken as a runbook to run. `go` is removed, with no alias. Bare `paulrun` still shows help.
7. **Command names win over book names.** `paulrun check` is always the `check` command, even if there's a `check.md` book. `paulrun run check` reaches the book.
8. No new runtime dependencies.

Decisions 1 and 2 are a breaking change for anyone who runs a runbook by its path from another folder. Decision 6 is a breaking change for everyone who types `paulrun go`. The CHANGELOG says both plainly.

The library wording, `paulrun library` (was `paulrun books`) and `PAULRUN_LIBRARY` (was `PAULRUN_RUNBOOKS`) were changed by Paul on 2026-10-13, after approval and before Task 4.

Decisions 6 and 7 (`run` replacing `go`, and running a runbook with no command) were added by Paul on 2026-10-14, after Task 5 (plan Task 5b).

## Runbook format changes

This section is the sign-off SPEC.md's Boundaries require for format changes.

### Where blocks run

- Every block runs with paulrun's starting folder as its working directory. This is the same for every backend, and the backend protocol doesn't change.
- Every block's environment has `PAULRUN_RUNBOOK_DIR`, the absolute path of the folder the runbook file is in. This is for runbooks that need files kept next to them, e.g. `"$PAULRUN_RUNBOOK_DIR/templates/pr.md"`. It's an environment variable, not an input, so `<PAULRUN_RUNBOOK_DIR>` stays an undeclared-placeholder error.
- The run overview shows the folder blocks will run in, on a `directory: <path>` line after the title. This is shown under `--dry` too, so you see where `rm -rf node_modules` will run before you answer `Start?`.

### `default` on inputs

```yaml
inputs:
  - name: FE_SET
    description: Which frontend set to rebuild
    choices: [comms, billing, all]
    default: comms
```

- The prompt shows the default, and pressing enter takes it.
- The environment still comes first (0.1.0 Decision 3): with `FE_SET=all` set, paulrun uses `all` and doesn't ask.
- `default` must be a YAML string. `default: 1.10` is a `check` error that says to quote it, because YAML would read it as the number `1.1`.
- A secret can't have a default, because it would be written in plain text in the runbook. That's a `check` error.
- A default that doesn't match the input's `pattern`, or isn't one of its `choices`, is a `check` error.
- Works the same in `input` blocks.

### `choices` on inputs

- A non-empty YAML list of strings. You type the value itself, not a number.
- The prompt lists the choices. Any other answer is asked again, with `FE_SET must be one of: comms, billing, all`.
- A value from the environment that isn't one of the choices stops the run before anything runs, the same as a `pattern` mismatch: `FE_SET from the environment must be one of: comms, billing, all`.
- `check` errors:
  - `choices` isn't a list of strings, or is empty
  - the input is secret, because its choices would be written in the runbook
  - a choice doesn't match the input's `pattern`, so it could never be accepted
- `choices` and `pattern` can be used together, and a value must pass both.
- Works the same in `input` blocks.

## Commands (CLI)

```
paulrun RUNBOOK [--dry] [--step]        # the same as paulrun run RUNBOOK
paulrun run [RUNBOOK] [--dry] [--step]  # replaces go; RUNBOOK is a path or a book's name; no RUNBOOK picks from the library
paulrun check RUNBOOK                   # RUNBOOK is a path or a book's name
paulrun inputs RUNBOOK                  # RUNBOOK is a path or a book's name; now shows default and choices
paulrun library                         # new: list the books in the runbook library
paulrun backends
paulrun --version
paulrun                                 # with nothing else, shows help, as before
```

**Running without `run`:** when the first argument isn't a command name or `--help`/`--version`, paulrun runs it as if `run` came first. Options work either side of it, so `paulrun deploy --dry` and `paulrun --dry deploy` are the same. `paulrun --help` shows the usage as `paulrun [OPTIONS] RUNBOOK | COMMAND [ARGS]...`, and lists `run` with the other commands.

- Name lookup, errors and exit codes are exactly those of `paulrun run`. E.g. a name that's neither a file nor a book is a usage error, exit 2.
- A misspelt command, e.g. `paulrun chekc deploy`, is read as a runbook called `chekc`. That's the cost of making `run` optional. The not-found error names the runbook it looked for, so the typo is visible.
- `paulrun library` marks a book whose name is also a command, e.g. `check  (run it with paulrun run check)`, since `paulrun check` won't run it.

**Name lookup** (`run`, `check`, `inputs`) follows Decision 5. When nothing is found, the error names both places looked in, e.g. `no runbook 'rebuild-frontend': no such file here, and no rebuild-frontend.md in the library at /Users/paul/runbooks`. That's a usage error, exit 2, the same as a missing file in 0.1.0.

**`paulrun library`** prints where the library is, then one entry per book sorted by name, laid out like `paulrun inputs`:

```
library: /Users/paul/runbooks
rebuild-frontend     Rebuild the frontend
                     Clean install the frontend's dependencies, then rebuild it.
update-project-deps  Update a project's dependencies
```

- The first line of each entry is the book's name and title. A book with no title shows its name alone.
- The description goes underneath when there is one.
- Only the frontmatter is read, so a broken body doesn't hide a book.
- A book whose frontmatter can't be read is still listed, with the reason, and the listing carries on.
- An empty or missing library prints `no books in the library at <folder>`, with a hint about `PAULRUN_LIBRARY`, and exits 0.

**The picker:** `paulrun run` with no RUNBOOK lists the library's books numbered, `  1. rebuild-frontend  Rebuild the frontend`, and asks `Run which?`.

- Answering a number carries on exactly like `paulrun run <name>`: check, inputs, overview, `Start? [y/N]`. `--dry` and `--step` apply.
- Anything that isn't a listed number is asked again.
- Pressing enter with no answer ends without running anything, exit 1, the same as answering no to `Start?`. So does Ctrl-C. No transcript is written either way.
- With no books in the library, it's an error, exit 1, saying where the library is.
- Only `run` has a picker. `check` and `inputs` still need a RUNBOOK. Bare `paulrun` shows help, not the picker.

**`paulrun inputs`** adds `default: comms` and `choices: comms, billing, all` detail lines, beside the existing `pattern:` and `secret` ones.

Exit codes are unchanged: 0 success, 1 failure, 2 usage error.

## Documentation

Every feature is documented in the same change that builds it (SPEC.md Boundaries).

- **New page, `docs/library.md`** ("📚 Your runbook library"), added to the mkdocs nav. It covers:
  - the library, where it is, and `PAULRUN_LIBRARY`
  - running a book by name, with paths winning over names
  - `paulrun library` and the picker
  - why blocks run where you are
  - `PAULRUN_RUNBOOK_DIR`
- **A worked example on that page:** a runbook that clean-installs a frontend's dependencies under nvm and rebuilds it. It uses `source "$NVM_DIR/nvm.sh"` to show how to use shell functions your profile normally loads. It also shows that a block's `cd` and `PATH` changes only last for that block. The example uses generic paths and commands, not the work repo's.
- **`docs/runbook-format.md`:**
  - `default` and `choices` under Inputs
  - a "Where blocks run" section
  - transcript paths now relative to where paulrun was started
- **`docs/cli.md`:**
  - `run` in place of `go`, and running a runbook with no command
  - name lookup for `run`, `check` and `inputs`
  - the picker
  - a `paulrun library` section
  - `PAULRUN_LIBRARY`
- **`README.md` and `docs/index.md`:** a short "Your runbook library" section, with the library in the feature list.
- **`CHANGELOG.md` and `docs/CHANGELOG.md`:** a `## 0.2.0` section that leads with the runbook library, the key feature, then the breaking change from Decisions 1 and 2.

## Project structure

Only what's new or changes:

```
paulrun/
  library.py       # new: where the library is, finding a book by name, listing its books
  cli.py           # run (was go), running with no command, run/check/inputs take a name, the picker, the library command
  inputs.py        # default and choices in Input and collect
  runbook.py       # parse default and choices
  validate.py      # default and choices checks
  runner.py        # blocks run in the starting folder, PAULRUN_RUNBOOK_DIR, directory in the overview
  transcript.py    # output_path relative to the starting folder
tests/
  library/         # a fixture library, for name lookup, paulrun library and the picker
  runbooks/        # readable examples for default and choices, plus a broken fixture per new check error
  test_library.py
docs/
  library.md
```

## Code style

As SPEC.md: plain functions and frozen dataclasses. The starting folder is read once in `cli.py` and passed down. Modules other than `cli.py` never call `os.getcwd()` or read `PAULRUN_LIBRARY` themselves, so tests can pass both in.

```python
@dataclass(frozen=True)
class Input:
    name: str
    description: str
    pattern: str | None = None
    secret: bool = False
    default: str | None = None
    choices: tuple[str, ...] = ()


def find(argument: str, cwd: Path, library: Path) -> Path | None:
    """The runbook an argument names: a file that exists, else the book <name>.md in the library."""
```

## Testing strategy

As SPEC.md, plus:

- **Isolation:** an autouse fixture points `PAULRUN_LIBRARY` at an empty temporary folder, so a developer's real library at `~/runbooks` never affects a test. Tests that need a library point it at `tests/library/`.
- **Starting folder:** tests for where blocks run start paulrun in one temporary folder, with the runbook in another. They check that blocks and the transcript land in the starting folder, and that `PAULRUN_RUNBOOK_DIR` points to the runbook's folder.
- **Fixtures:** each new `check` error gets a broken fixture in `tests/runbooks/broken/`, and `default` and `choices` each get a readable example in `tests/runbooks/`.
- **Existing tests:** tests that relied on blocks running in the runbook's folder, e.g. `test_go_runs_blocks_in_the_runbook_directory`, are changed to the new rule, not deleted.

## Boundaries

As SPEC.md, plus:

**Always:**
- Document each feature in the same change that builds it
- Keep `PUBLISHING.md` and `examples/clientele-publishing.md` working unchanged when run from their repo root

**Ask first:**
- Anything beyond this spec, including the items in Out of scope

**Never:**
- Read from or write to the real library at `~/runbooks` in tests
- Put a secret's value in a `default` or `choices`, or show it in `paulrun library` or `paulrun inputs`

## Out of scope for 0.2.0

- A config file, or more than one library
- Subfolders (shelves) in the library
- Shell setup features (loading a profile, nvm or similar); this is covered by documentation only
- A `check` warning for `cd` or `export` at the end of a block
- Resuming with `--from`
- Carrying state between blocks, or saving a block's output in a variable
- Loading `.env` files
- `--yes`, or any non-interactive / CI mode
- A picker for `check` or `inputs`
- Picking a choice by number

## Success criteria

- [ ] With `PAULRUN_LIBRARY` set to a folder, `paulrun run <name>`, `paulrun check <name>` and `paulrun inputs <name>` use the book `<folder>/<name>.md`, with or without a trailing `.md`
- [ ] Without `PAULRUN_LIBRARY`, or with it empty, the library is `~/runbooks`
- [ ] An existing file is used before a book of the same name; an argument with a `/` is never looked up in the library
- [ ] A name that isn't found exits 2, naming both places looked in
- [ ] Blocks run in the starting folder, for a local runbook and a book from the library, in shell and Python blocks
- [ ] `PAULRUN_RUNBOOK_DIR` in a block is the runbook file's folder
- [ ] A relative `output_path` is written under the starting folder; an absolute one is unchanged
- [ ] The overview, and `--dry`, show `directory: <starting folder>`
- [ ] `paulrun library` lists each book's name, title and description in name order, still lists one with unreadable frontmatter, ignores subfolders and non-`.md` files, and says so when there are none
- [ ] `paulrun run` with no RUNBOOK runs the book picked by number, works with `--dry` and `--step`, and asks again after an answer that isn't a listed number. A blank answer or Ctrl-C runs nothing, writes no transcript and exits 1
- [ ] Enter at a prompt with a `default` takes the default; the environment overrides it
- [ ] An answer that isn't one of the `choices` is asked again; an environment value that isn't one fails before anything runs
- [ ] `check` errors on:
  - a non-string default
  - a default or choices on a secret
  - a default failing its pattern or choices
  - choices that aren't a non-empty list of strings
  - a choice failing its pattern
- [ ] `default` and `choices` work in `input` blocks, and `paulrun inputs` shows both
- [ ] `docs/library.md` exists with the worked nvm example. `docs/runbook-format.md`, `docs/cli.md`, `README.md` and the CHANGELOG cover everything above
- [ ] The docs tests check the new examples
- [ ] No new runtime dependencies
- [ ] Paul runs his own frontend rebuild book from his library in the work repo, and it completes
- [ ] `paulrun RUNBOOK` runs exactly as `paulrun run RUNBOOK` does, with options before or after it; `paulrun go` is no longer a command; bare `paulrun` shows help
- [ ] A command name is never read as a runbook, and `paulrun library` marks a book whose name is a command
- [ ] paulrun 0.2.0 is released with an unchanged `PUBLISHING.md`, run as `paulrun PUBLISHING.md`

## Open questions

None, once the decisions above are approved.
