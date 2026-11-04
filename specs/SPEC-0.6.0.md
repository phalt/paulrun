# Spec: paulrun 0.6.0

Status: approved (2026-11-04)
Version target: 0.6.0

This builds on [SPEC-0.3.0.md](SPEC-0.3.0.md), [SPEC-0.2.0.md](SPEC-0.2.0.md) and [SPEC.md](SPEC.md). Anything not mentioned here is unchanged.

## Objective

Make `paulrun run`'s terminal output easy to scan: the overview, each step, each block's output and the result should never look alike. The transcript is unchanged.

**User:** Paul.

### User stories

- As Paul, I can tell at a glance where a step starts, where a block's output starts and ends, and whether it passed.
- As Paul, I see what a block printed, not its code, unless I ask for the code with `--show-code`.
- As Paul, I can tell what a block wrote to stderr from what it wrote to stdout.

## Decisions

1. **Colour has one meaning each.** Blue is structure (the overview box and step rules), green is success, yellow is a confirm or a dry run, red is failure only. Frames, times and docstrings are dim. Paul chose blue for steps, over magenta and white, after seeing both dark and light themes (2026-11-04).
2. **The overview is boxed:** dim labels `directory`, `inputs`, `steps`, `blocks`, with the title on the border.
3. **A step is a full-width bold blue rule,** `n/total  Name`.
4. **Docstrings are dim italic. Confirms are in a yellow box** titled `confirm`.
5. **A block is a bracket.** `┌ <language> · HH:MM:SS.mmm` opens it, each line of output follows `│ `, and `└ ✓ exit 0 · 0.0s` (green) or `└ ✗ exit 3 · 0.0s` (red) closes it. A skipped block closes with `└ ↷ skipped`. This replaces `=== LOG: … ===` and `========`.
6. **Code is hidden by default.** `--show-code` shows it in cyan inside the bracket, with `├ output` before the output. `--dry` always shows code. `--step` doesn't: Paul chose this (2026-11-04).
7. **stderr is marked with a red `│`;** the line itself is the normal colour.
8. **The run ends with a box:** `✓ finished ok`, `✗ failed at "Step" (exit 3)`, `✗ aborted …`, `✗ interrupted …` or `dry run, nothing was run`, with a green, red or yellow border and a dim duration.
9. **The transcript doesn't change.** It still has full code and full ISO times (2026-11-04).
10. **Backends stay compatible.** `output` takes an optional `stderr=False` keyword, so a backend that calls `output(line)` still works. `stream()` reads stdout and stderr from separate pipes, so lines written to both at almost the same moment can come out in a different order.
11. No new runtime dependencies.
