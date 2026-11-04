"""Helpers for matching run's terminal output, whose boxes and rules change width with what's in them."""

import re


def normalized(output: str) -> str:
    """run's output with the parts that change from run to run, or with the box's contents, made the same.

    The directory is DIR, durations are Xs, a box's padding and borders are as short as they can be, and a step's
    rule is one ━. Docs show real output and tests write it short; both match once normalized.
    """
    output = re.sub(r"^│ directory  .*?( *│)$", r"│ directory  DIR\1", output, flags=re.MULTILINE)
    output = re.sub(r"· (\d+m)?\d+(\.\d)?s\b", "· Xs", output)
    output = re.sub(r"^(│.*?) +│$", r"\1 │", output, flags=re.MULTILINE)
    output = re.sub(r"─+([╮╯])$", r"─\1", output, flags=re.MULTILINE)
    return re.sub(r"━+$", "━", output, flags=re.MULTILINE)


def printed(output: str) -> list[str]:
    """The lines inside run's block brackets, code or output, without the │ in front of them."""
    return [line.removeprefix("  │").removeprefix(" ") for line in output.splitlines() if line.startswith("  │")]


def title(output: str) -> str:
    """The runbook's title, from the top of run's overview box."""
    first = next(line for line in output.splitlines() if line.startswith("╭─ "))
    return first.removeprefix("╭─ ").rstrip("─╮").rstrip()


def finished(output: str) -> str:
    """How the run finished, from the box at the end of run's output."""
    lines = output.splitlines()
    bottom = max(at for at, line in enumerate(lines) if line.startswith("╰"))
    return lines[bottom - 1].strip("│").strip()
