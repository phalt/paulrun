# Implementation Plan: paulrun 0.6.0

Status: approved (2026-11-04)
Spec: [specs/SPEC-0.6.0.md](../specs/SPEC-0.6.0.md)
Tasks: [tasks/todo-0.6.0.md](todo-0.6.0.md)

## Overview

Redesign `_Printer` in `cli.py`, add `--show-code`, and carry stderr from the backends to the printer.

## Architecture decisions

- **Only the printer changes for the look.** `runner` events stay as they are, apart from `OutputLine` gaining `stderr: bool = False`. The transcript ignores it.
- **rich renders the boxes and rules** (`Panel`, `Rule`, `Table.grid`). Text from runbooks and blocks is always `Text`, never markup.
- **Code shown is a printer setting:** `_Printer(show_code=...)`, `True` under `--dry`.
- **stderr goes through the existing callback.** `output(line, stderr=False)`, so third-party backends that call `output(line)` keep working. `stream()` uses two pipes and `selectors`, keeping its Ctrl-C handling.

## Task list

Full task bodies are in [todo-0.6.0.md](todo-0.6.0.md).

1. Boxed overview, numbered step rules, dim docstrings, confirm box
2. Block brackets with language, time and ✓/✗ exit; end-of-run boxes
3. `--show-code`, implied by `--dry`
4. stderr marked in the terminal
5. Docs and changelog
