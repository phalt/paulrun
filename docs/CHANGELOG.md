# Change log

## 0.2.0

### A runbook library
- keep runbooks you use across projects in `~/runbooks`, or wherever `PAULRUN_LIBRARY` says. Then run one by name from anywhere, e.g. `paulrun rebuild-frontend`. `run`, `check` and `inputs` all take a book's name as well as a path, and a file where you are is always used before a book with the same name. `paulrun library` lists the books in your library, with each one's title and description. `paulrun run`, with no runbook, lists them by number and runs the one you pick.

- **Breaking:** `paulrun go` is now `paulrun run`, and you don't need to type it: `paulrun RELEASING.md` runs `RELEASING.md`. Anything after `paulrun` that isn't a command is a runbook to run, so `paulrun go` is no longer a command. `paulrun` on its own still shows help.
- **Breaking:** blocks now run in the folder you run paulrun from, not the folder the runbook is in. A relative `output_path` is now relative to that folder too. A runbook kept at the root of its project, run from there, works as before. One run as `paulrun path/to/RUNBOOK.md` from another folder now works on that other folder and writes its transcript there. This includes blocks run by external backends, whose `cwd` is now the folder paulrun was started from.
- Blocks get `PAULRUN_RUNBOOK_DIR`, the folder the runbook is in, so a runbook can still use files kept next to it.
- Running a runbook shows the folder blocks will run in, as `directory:` straight after the title, so you can check it before answering `Start?`. `--dry` shows it too.
- Inputs can have a `default`, shown at the prompt and used when you press enter. The environment still comes first. `check` reports a default that isn't text, doesn't match the input's `pattern`, or is on a secret.
- Inputs can have `choices`: the only values accepted, listed at the prompt. You type the choice itself, and a value from the environment has to be one of them too. `check` reports choices that aren't a list of text, a choice the `pattern` refuses, a default that isn't a choice, and choices on a secret.

## 0.1.0

Initial release. paulrun runs hand-written markdown runbooks.

- `paulrun go` runs a runbook's steps in order, streaming each block's output as it's printed and stopping at the first block that fails.
- `run` blocks for shell (`sh`, `bash`, `shell`) and Python (`python`, `py`), with the `python` frontmatter key to choose the interpreter.
- `docstring` blocks to show notes as the runbook runs, and `confirm` blocks to pause for steps done by hand.
- `input` blocks to ask for a value part way through a run, once it exists: a pull request number from a step done by hand, or a one-time code that expires in seconds.
- Inputs, collected from the environment or by asking, with an optional `pattern` to check them against. Plain inputs fill in `<NAME>` placeholders; secrets are hidden as you type them and replaced with `****` everywhere paulrun shows or records them.
- `paulrun go --dry` to see every block with its inputs filled in, without running anything.
- `paulrun go --step` to run, skip or quit at each block.
- Transcripts: with `output_path` set, every run is added to a plain record of what ran, what it printed and how it finished.
- Ctrl-C stops a run cleanly, letting a running block stop and recording how far the run got.
- `paulrun check` to find problems before running anything: missing or malformed frontmatter, undeclared placeholders, secrets used as placeholders, blocks outside a step, and shell and Python syntax errors, with shellcheck warnings when it's installed.
- `paulrun inputs` to list the inputs a runbook needs, and `paulrun backends` to list the languages paulrun can run.
- Backends for other languages can be added by any package, through the `paulrun.backends` entry point group.
