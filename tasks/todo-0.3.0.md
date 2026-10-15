# paulrun 0.3.0 tasks

Plan: [tasks/plan-0.3.0.md](plan-0.3.0.md). Spec: [specs/SPEC-0.3.0.md](../specs/SPEC-0.3.0.md).

Every task also clears the standing bar:
- `make format`, `make ty` and `make test` are clean
- the `## 0.3.0` section of `CHANGELOG.md`, copied to `docs/CHANGELOG.md`, covers anything user-visible
- `docs/runbook-format.md` and `docs/cli.md` are updated in the same change as the behaviour they describe
- each new feature has a readable example in `tests/runbooks/`, used by the CLI tests

---

## Task 1: `step` in the frontmatter, and `--no-step`

**Description:** A runbook can set `step: true` to run as if `--step` was given.
- `Runbook` gets `step: bool`, read by `parse` as `bool(frontmatter.get("step", False))`.
- `CORE_KEYS` gains `step`, and `check` errors with `step must be true or false` on anything that isn't a YAML boolean.
- `run`'s `--step` becomes `--step/--no-step` with `default=None`. With neither, `parsed.step` decides.
- A skipped block is shown and recorded as `skipped`, not `skipped (--step)`.
- Add `tests/runbooks/step-frontmatter-example.md` and `tests/runbooks/broken/step-not-true-or-false.md`.

**Acceptance criteria:**
- [x] `step: true` asks before each run block without `--step`, with the same output as `--step`
- [x] `--no-step` runs it straight through, before or after the runbook, with or without `run`; on a runbook without `step`, it changes nothing
- [x] `--dry` asks nothing for a `step: true` runbook
- [x] `check` reports `step: always`, `step: 1` and `step: 'true'` on their line

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_runbook.py tests/test_validate.py tests/test_cli.py tests/test_transcript.py`
- [ ] Manual check: `uv run paulrun tests/runbooks/step-frontmatter-example.md`, then again with `--no-step`

**Dependencies:** None

**Files likely touched:**
- `paulrun/runbook.py`, `paulrun/validate.py`, `paulrun/cli.py`, `paulrun/transcript.py`
- `tests/test_runbook.py`, `tests/test_validate.py`, `tests/test_cli.py`, `tests/test_transcript.py`
- `tests/runbooks/step-frontmatter-example.md`, `tests/runbooks/broken/step-not-true-or-false.md`
- `docs/runbook-format.md`, `docs/cli.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Small

## Task 2: `q` to quit the picker

Added 2026-10-15, at Paul's request, while Task 1 was being built.

**Description:** At `Run which?`, `q` quits, the same as a blank answer. The question says so: `Run which? (q to quit)`, with `(q to quit)` dim in a terminal. A wrong answer says `Pick a number from 1 to N, or q to quit.`

**Acceptance criteria:**
- [x] `q` runs nothing, writes no transcript and exits 1
- [x] `q` quits even when the library has a `q.md`
- [x] The question and the wrong-answer message mention `q`

**Verification:**
- [x] Tests pass: `uv run pytest tests/test_cli.py -k picker`
- [ ] Manual check: `PAULRUN_LIBRARY=tests/library uv run paulrun run`, then `q`

**Dependencies:** None

**Files likely touched:**
- `paulrun/cli.py`
- `tests/test_cli.py`
- `docs/cli.md`, `docs/library.md`, `CHANGELOG.md`, `docs/CHANGELOG.md`

**Estimated scope:** Small
