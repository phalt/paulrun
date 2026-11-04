# paulrun 0.6.0 tasks

Plan: [tasks/plan-0.6.0.md](plan-0.6.0.md). Spec: [specs/SPEC-0.6.0.md](../specs/SPEC-0.6.0.md).

Every task also clears the standing bar:
- `make format`, `make ty` and `make test` are clean
- the `## 0.6.0` section of `CHANGELOG.md`, copied to `docs/CHANGELOG.md`, covers anything user-visible
- examples of `run`'s output in `README.md` and `docs/` show it as it is

---

## Task 1: Overview, steps, docstrings and confirms

**Acceptance criteria:**
- [ ] The overview is a blue box with the title on its border and dim labels
- [ ] Each step is a bold blue rule, `n/total  Name`
- [ ] Docstrings are dim italic; confirms are in a yellow box titled `confirm`

## Task 2: Blocks and the end of the run

**Acceptance criteria:**
- [ ] A block opens with `┌ <language> · HH:MM:SS.mmm`, its output follows `│ `, and `└ ✓/✗ exit N · Xs` closes it
- [ ] A skipped block closes with `└ ↷ skipped`
- [ ] The run ends in a box for ok, failed, aborted, interrupted and dry
- [ ] The transcript is unchanged

## Task 3: `--show-code`

**Acceptance criteria:**
- [ ] Code is hidden by default, and shown in cyan with `--show-code`, then `├ output`
- [ ] `--dry` always shows code; `--step` doesn't

## Task 4: stderr

**Acceptance criteria:**
- [ ] `stream()` passes stderr lines to `output(line, stderr=True)`, live, with Ctrl-C handled as before
- [ ] A backend calling `output(line)` still works
- [ ] stderr lines have a red `│` in the terminal; the transcript is unchanged

## Task 5: Docs and changelog

**Acceptance criteria:**
- [ ] `README.md`, `docs/index.md`, `docs/cli.md` show the new output, and `docs/cli.md` documents `--show-code`
- [ ] `docs/backends.md` documents `stderr=` and the ordering caveat
- [ ] `CHANGELOG.md` and `docs/CHANGELOG.md` have a `## 0.6.0` section
