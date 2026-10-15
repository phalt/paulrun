# Spec: paulrun 0.3.0

Status: approved (2026-10-15)
Version target: 0.3.0

This builds on [SPEC-0.2.0.md](SPEC-0.2.0.md) and [SPEC.md](SPEC.md). Anything not mentioned here is unchanged.

## Objective

Two small changes to running a runbook.

**User:** Paul.

### User stories

- As Paul, I mark a runbook that should never run straight through (one that changes production, say) with `step: true`, and every run asks before each block without anyone remembering `--step`.
- As Paul, I run that runbook straight through when I know what I'm doing, with `--no-step`.
- As Paul, I type `q` at the book picker to quit, instead of working out that Ctrl-C or a blank answer does it.

## Decisions

1. **`step: true` turns stepping on by default.** It's not forced: `--no-step` turns it off for one run. Paul chose the default over forcing it (2026-10-15).
2. **The command line wins over the frontmatter.** `--step` steps and `--no-step` doesn't, whatever the runbook says. With neither, the runbook's `step` decides, and a runbook without it runs straight through, as before.
3. **`--dry` still ignores stepping,** from the flag or the frontmatter, since nothing runs.
4. **`q` at the picker quits,** the same as a blank answer: nothing runs, no transcript is written, exit 1. Books are picked by number, so a book called `q.md` doesn't change this.
5. No new runtime dependencies.

## Runbook format changes

This section is the sign-off SPEC.md's Boundaries require for format changes.

### `step` in the frontmatter

```yaml
---
title: Migrate production
step: true
---
```

- Optional, default `false`.
- With `true`, a run asks `Run this block? [y]es / [s]kip / [q]uit` before each `run` block, exactly as `--step` does.
- `step` must be a YAML boolean. Anything else, e.g. `step: always` or `step: 'true'`, is a `check` error: `step must be true or false`. If it's run anyway, a truthy value steps, so a malformed value can only make a run ask more, never less.

### Skipped blocks

A block skipped by answering `s` is shown and recorded in the transcript as `skipped`, not `skipped (--step)`, since `step: true` skips blocks too. This changes the transcript format by one line.

## Commands (CLI)

```
paulrun RUNBOOK [--dry] [--step | --no-step]
paulrun run [RUNBOOK] [--dry] [--step | --no-step]
```

- `--no-step` is new. On a runbook without `step: true`, it does nothing.
- The picker's question is `Run which? (q to quit)`, with `(q to quit)` dim in a terminal. A wrong answer says `Pick a number from 1 to N, or q to quit.`

Exit codes are unchanged.

## Documentation

- `docs/runbook-format.md`: `step` in the frontmatter example and table; the transcript example's `skipped` line.
- `docs/cli.md`: `--no-step` in the usage, `step: true` under `--step`, `q` in the picker.
- `docs/library.md`: the picker's question.
- `CHANGELOG.md` and `docs/CHANGELOG.md`: a `## 0.3.0` section.

## Testing strategy

As the earlier specs. `step: true` gets a readable example, `tests/runbooks/step-frontmatter-example.md`, and the new `check` error a broken fixture, `tests/runbooks/broken/step-not-true-or-false.md`.

## Out of scope for 0.3.0

- Forcing stepping so it can't be turned off
- Stepping per step or per block, e.g. a `step` key on a `run` block
- Picking a book by name at the picker

## Success criteria

- [x] A runbook with `step: true` asks before each run block without `--step`, with the same output as with `--step`
- [x] `--no-step` runs it straight through, before or after the runbook, with or without `run`
- [x] `--dry` asks nothing for a runbook with `step: true`
- [x] `check` reports a `step` that isn't a boolean, on its line
- [x] Skipped blocks show and are recorded as `skipped`
- [x] `q` at the picker runs nothing, writes no transcript and exits 1, even with a `q.md` book; the question says `(q to quit)`
- [x] Docs and CHANGELOG cover all of the above
- [x] Paul approves the format change (approved 2026-10-15)

## Open questions

None.
