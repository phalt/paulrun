# Implementation Plan: paulrun 0.1.0

Status: approved (2026-10-07)
Spec: [specs/SPEC.md](../specs/SPEC.md)
Tasks: [tasks/todo.md](todo.md)

## Overview

Build `paulrun` 0.1.0 as described in the spec: a Click + rich CLI that parses hand-written markdown runbooks, validates them (`check`), and runs their `run` blocks through pluggable backends (`go`, with `--dry` and `--step`), writing an optional appended transcript. Project layout, tooling and docs mirror clientele.

The order is: scaffold, then a thin end-to-end walking skeleton (`paulrun go` runs a single shell block), then widen it one feature at a time. Each task leaves `main` green and `paulrun` runnable.

## Architecture decisions

- **Walking skeleton first.** The riskiest part is executing a block while streaming its output live to the terminal *and* capturing it for the transcript. Task 5 proves that with the shell backend before inputs, validation or the transcript exist.
- **One parse, many consumers.** `runbook.py` turns a file into an immutable `Runbook` (frontmatter, inputs, steps, blocks with line numbers). `check`, `go`, `inputs` and `backends` all consume that model; nothing re-parses markdown.
- **Validation is one function.** `check` and step 1 of `go` call the same `validate(runbook, backends) -> Report` (errors + warnings), so they can never disagree.
- **Backends stream lines.** `Backend.run()` yields output lines and finishes with an exit code (exact shape settled in Task 4). The runner owns printing, masking and transcript writing; backends never touch the console.
- **Subprocess model.** `Popen` with stdout and stderr merged into one pipe, read line by line, stdin inherited from the terminal. Merged streams keep ordering simple and match how the transcript shows output.
- **Entry points everywhere.** The built-in shell and Python backends are registered in paulrun's own `pyproject.toml`, so built-ins and external backends share one loading path. The loader takes an optional list of entry points so tests can inject a fake external backend without installing a package.
- **Console only in `cli.py`.** Library modules return data or raise. Prompts (inputs, confirms, `--step`) go through a small injectable `Prompter` so the runner is testable without a TTY.

## Dependency graph

```
scaffold (1) ── tooling + CI (2)
   │
runbook parser (3)
   │
backend loader + shell backend (4)
   │
runner + `paulrun go` walking skeleton (5)
   │
   ├── inputs (6) ──┬── docstring/confirm/failure handling (7) ── --dry (8)
   │                │
   │                └── python backend + `python:` key (9)
   │
   └── validate + `paulrun check` (10)   [needs 6, 9]
          │
          ├── --step (11)
          ├── transcript (12)
          └── `inputs` + `backends` commands, external backend test (13)
                 │
       docs site (14) ── README + project docs (15) ── examples + own PUBLISHING.md (16)
```

## Task list

Full task bodies (acceptance criteria, verification, files) are in [todo.md](todo.md).

### Phase 1: Foundation
- [x] Task 1: Package skeleton with `paulrun --version`
- [x] Task 2: Dev tooling and CI, matching clientele
- [x] Task 3: Runbook parser

### Checkpoint 1: Foundation
- [ ] `make test`, `make ty`, `make format` clean; CI green on `main`
- [x] Parser handles `tests/runbooks/all_features.md`

### Phase 2: Walking skeleton
- [ ] Task 4: Backend protocol, entry point loader, shell backend
- [ ] Task 5: Runner and `paulrun go` (shell blocks only)

### Checkpoint 2: Walking skeleton
- [ ] `paulrun go` on a two-step shell runbook streams output live and stops on failure
- [ ] Review with Paul before widening

### Phase 3: Core features
- [ ] Task 6: Inputs: declare, collect, validate, substitute, mask
- [ ] Task 7: `docstring` and `confirm` blocks, start prompt, exit codes
- [ ] Task 8: `--dry`
- [ ] Task 9: Python backend and the `python:` frontmatter key
- [ ] Task 10: Validation and `paulrun check`

### Checkpoint 3: Core features
- [ ] `paulrun check` and `paulrun go --dry` work on `tests/runbooks/all_features.md`
- [ ] All `check` error cases from the spec covered by fixture tests

### Phase 4: Remaining features
- [ ] Task 11: `--step`
- [ ] Task 12: Transcript (`output_path`)
- [ ] Task 13: `paulrun inputs`, `paulrun backends`, external backend test

### Checkpoint 4: Feature complete
- [ ] Every code-level success criterion in the spec has a passing test
- [ ] Review with Paul

### Phase 5: Docs and dogfooding
- [ ] Task 14: mkdocs site
- [ ] Task 15: README, CONTRIBUTING, CHANGELOG and project docs
- [ ] Task 16: Examples and paulrun's own PUBLISHING.md

### Checkpoint 5: Ready to release (Paul only)
- [ ] Paul releases clientele with `paulrun go PUBLISHING.md`
- [ ] Paul releases paulrun 0.1.0 with its own PUBLISHING.md
- [ ] Docs deployed to `phalt.github.io/paulrun`

Agents never publish to PyPI or deploy docs (spec Boundaries).

## Parallelisation

Mostly sequential: almost everything hangs off the parser, runner and inputs. After Checkpoint 3, Tasks 11, 12 and 13 are independent and could run in parallel. Task 14 (docs site) can start any time after Task 10, since the runbook format is fixed by then.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Live streaming and capture interfere (buffering, rich mangling output, lost lines) | High | Proved first in Task 5. Read raw lines from the pipe, print with `markup=False, highlight=False`. Set `PYTHONUNBUFFERED=1` in block env so Python child output isn't held back |
| Interactive commands inside `run` blocks (a credentials prompt, a pager) hang or hide their prompt because stdout is piped | Medium | stdin is inherited so input still works. Set `GIT_PAGER=cat` and `PAGER=cat` in block env. Document in `runbook-format.md` that `run` blocks should be non-interactive and secrets should come through `inputs` |
| A secret is split across lines or reformatted by a tool, so line-based masking misses it | Medium | Mask on every line, plus mask the full transcript text before each write. Accept that a tool that transforms the secret (e.g. base64s it) isn't covered; note it in docs |
| `<NAME>` placeholder regex hits something that isn't a placeholder (e.g. `<HTML>` in a heredoc) | Low | Only flagged if undeclared, as a `check` error with line number; the fix is obvious. Revisit if it bites |
| Entry points for paulrun's own backends missing in a fresh checkout | Low | `make install` (`uv sync`) installs the package in editable mode, which registers them. CI runs `uv sync --frozen` first |
| `ty` is pre-1.0 and may flag false positives | Low | Same approach as clientele: targeted excludes in `[tool.ty.src]` rather than suppressing everywhere |

## Resolved questions

1. **CI matrix:** match clientele (`3.12`, `3.13`, `3.14`, `3.15-dev`).
2. **Codecov:** skipped. Coverage is reported in the CI log only.
3. **Platforms:** macOS and Linux only, stated in the README.
