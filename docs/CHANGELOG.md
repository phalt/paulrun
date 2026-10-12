# Change log

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
