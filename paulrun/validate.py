import re
import shlex
import shutil
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from paulrun.backends import Backend
from paulrun.inputs import PLACEHOLDER
from paulrun.runbook import Block, Runbook

CORE_KEYS = ("title", "description", "output_path", "python", "inputs")
INPUT_KEYS = ("name", "description", "pattern", "secret")
_UPPER_SNAKE_CASE = re.compile(r"[A-Z][A-Z0-9_]*")


@dataclass(frozen=True)
class Finding:
    line: int  # line in the runbook file
    message: str
    warning: bool = False


@dataclass(frozen=True)
class _Declared:
    secret: bool
    line: int  # file line of the input's entry


@dataclass(frozen=True)
class Report:
    findings: list[Finding]  # in line order

    @property
    def errors(self) -> list[Finding]:
        return [finding for finding in self.findings if not finding.warning]

    @property
    def warnings(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.warning]

    @property
    def ok(self) -> bool:
        """True if there are no errors. Warnings don't stop a runbook running."""
        return not self.errors


def validate(runbook: Runbook, backends: Mapping[str, Backend]) -> Report:
    """Find everything wrong with a runbook without running any of it."""
    findings = [
        *_frontmatter(runbook),
        *_inputs(runbook),
        *_placeholders(runbook),
        *_blocks(runbook, backends),
    ]
    return Report(sorted(findings, key=lambda finding: finding.line))


def _frontmatter(runbook: Runbook) -> Iterator[Finding]:
    frontmatter, lines = runbook.frontmatter, runbook.lines
    if "title" not in frontmatter:
        yield Finding(1, "title is required")
    for key in ("title", "description", "output_path", "python"):
        if key in frontmatter and not isinstance(frontmatter[key], str):
            yield Finding(lines.get(key, 1), f"{key} must be a string")
    if "inputs" in frontmatter and not isinstance(frontmatter["inputs"], list):
        yield Finding(lines.get("inputs", 1), "inputs must be a list")
    for key in frontmatter:
        if key not in CORE_KEYS:
            yield Finding(lines.get(key, 1), f"unknown frontmatter key {key!r}", warning=True)
    if runbook.python is not None and _uses_python(runbook):
        line = lines.get("python", 1)
        try:
            command = shlex.split(runbook.python)
        except ValueError as e:
            yield Finding(line, f"python command can't be read: {e}")
            return
        if not command:
            yield Finding(line, "python command is empty")
        elif shutil.which(command[0]) is None:
            yield Finding(line, f"python command {command[0]!r} isn't on PATH")


def _uses_python(runbook: Runbook) -> bool:
    return any(block.kind == "run" and block.language in ("python", "py") for block in _all_blocks(runbook))


def _inputs(runbook: Runbook) -> Iterator[Finding]:
    """Check each input entry as written in the frontmatter, including the ones the parser couldn't read."""
    entries = runbook.frontmatter.get("inputs")
    if not isinstance(entries, list):
        return
    for index, entry in enumerate(entries):
        line = runbook.lines.get(f"inputs.{index}", 1)
        if not isinstance(entry, dict):
            yield Finding(line, f"input {index + 1} must be a mapping with a name and description")
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            yield Finding(line, f"input {index + 1} needs a name")
        elif not _UPPER_SNAKE_CASE.fullmatch(name):
            yield Finding(line, f"input name {name!r} must be UPPER_SNAKE_CASE, e.g. {_upper_snake(name)}")
        label = name if isinstance(name, str) else str(index + 1)
        if not isinstance(entry.get("description"), str):
            yield Finding(line, f"input {label} needs a description")
        pattern = entry.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                yield Finding(line, f"input {label}'s pattern must be a string")
            else:
                try:
                    re.compile(pattern)
                except re.error as e:
                    yield Finding(line, f"input {label}'s pattern isn't a valid regex: {e}")
        for key in entry:
            if key not in INPUT_KEYS:
                yield Finding(line, f"unknown key {key!r} on input {label}", warning=True)


def _upper_snake(name: str) -> str:
    """A valid input name to suggest in place of name."""
    suggestion = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "NAME"
    # Names start with a letter, so give one that starts with a digit something to start with.
    return suggestion if suggestion[0].isalpha() else f"INPUT_{suggestion}"


def _placeholders(runbook: Runbook) -> Iterator[Finding]:
    """Every <NAME> must be a declared, non-secret input, and every input should be used somewhere."""
    declared = _declared(runbook)
    used: set[str] = set()
    for line, text, prefix in _placeholder_texts(runbook):
        for match in PLACEHOLDER.finditer(text):
            name = match.group(1)
            used.add(name)
            at = line + text.count("\n", 0, match.start())
            if name not in declared:
                yield Finding(at, f"{prefix}<{name}> isn't a declared input")
            elif declared[name].secret:
                yield Finding(
                    at,
                    f"{prefix}<{name}> is a secret, so it's never substituted; "
                    f"use ${name} to read it from the environment",
                )
    # A run block can also read an input from its environment, e.g. $TOKEN, so any mention of the name counts.
    for block in _all_blocks(runbook):
        if block.kind == "run":
            used.update(name for name in declared if re.search(rf"\b{re.escape(name)}\b", block.content))
    for name, entry in declared.items():
        if name not in used:
            yield Finding(entry.line, f"input {name} is never used", warning=True)


def _declared(runbook: Runbook) -> dict[str, _Declared]:
    """Each input entry with a string name, even if it has other errors.

    Using every named entry, not just the inputs the parser could read, means an input missing its
    description is reported once, rather than again for each placeholder that uses it.
    """
    entries = runbook.frontmatter.get("inputs")
    if not isinstance(entries, list):
        return {}
    return {
        entry["name"]: _Declared(bool(entry.get("secret", False)), runbook.lines.get(f"inputs.{index}", 1))
        for index, entry in enumerate(entries)
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }


def _placeholder_texts(runbook: Runbook) -> Iterator[tuple[int, str, str]]:
    """Each text placeholders are substituted into, with the file line its first line is on, and a message prefix."""
    if runbook.output_path is not None:
        yield runbook.lines.get("output_path", 1), runbook.output_path, "output_path: "
    for block in _all_blocks(runbook):
        # A block's first line is the one after its opening fence.
        yield block.line + 1, block.content, ""


def _blocks(runbook: Runbook, backends: Mapping[str, Backend]) -> Iterator[Finding]:
    for block in runbook.preamble:
        yield Finding(block.line, f"{block.kind} blocks must be inside a step (a ## heading)")
    for block in _all_blocks(runbook):
        if block.kind != "run":
            continue
        assert block.language is not None  # always set for run blocks
        backend = backends.get(block.language)
        if backend is None:
            yield Finding(block.line, f"no backend runs {block.language!r} blocks")
            continue
        for problem in backend.validate(block.content):
            # A backend counts block lines from 1, and the block's first line is the one after its fence.
            line = block.line if problem.line is None else block.line + problem.line
            yield Finding(line, problem.message, problem.warning)


def _all_blocks(runbook: Runbook) -> Iterator[Block]:
    """The preamble's blocks, then every step's, in file order."""
    yield from runbook.preamble
    for step in runbook.steps:
        yield from step.blocks
