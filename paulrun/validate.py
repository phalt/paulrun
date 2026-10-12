import re
import shlex
import shutil
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import yaml

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
class _Entry:
    """One input declaration as written: a frontmatter inputs item, or an input block's YAML."""

    value: Any  # the YAML as written, which may not be a valid input
    line: int  # file line of the entry, where its problems are reported
    label: str  # how to name it before its name is known, e.g. "input 2" or "input block"
    block: Block | None  # the input block it's from, or None if it's in the frontmatter

    @property
    def name(self) -> str | None:
        return self.value["name"] if isinstance(self.value, dict) and isinstance(self.value.get("name"), str) else None

    @property
    def secret(self) -> bool:
        return isinstance(self.value, dict) and bool(self.value.get("secret", False))


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
    """Check each input declaration as written, in the frontmatter or an input block, even ones the parser skipped."""
    first_seen: dict[str, int] = {}
    for entry in _entries(runbook):
        if isinstance(entry.value, _YamlError):
            yield Finding(entry.value.line, f"input block isn't valid YAML: {entry.value.problem}")
            continue
        if not isinstance(entry.value, dict):
            yield Finding(entry.line, f"{entry.label} must be a mapping with a name and description")
            continue
        name = entry.name
        if name is None:
            yield Finding(entry.line, f"{entry.label} needs a name")
        elif name in first_seen:
            # Only one value can be collected for a name, so a second declaration could never be used.
            yield Finding(entry.line, f"input {name} is declared twice (first on line {first_seen[name]})")
        elif not _UPPER_SNAKE_CASE.fullmatch(name):
            yield Finding(entry.line, f"input name {name!r} must be UPPER_SNAKE_CASE, e.g. {_upper_snake(name)}")
        if name is not None:
            first_seen.setdefault(name, entry.line)
        label = f"input {name}" if name is not None else entry.label
        if not isinstance(entry.value.get("description"), str):
            yield Finding(entry.line, f"{label} needs a description")
        pattern = entry.value.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                yield Finding(entry.line, f"{label}'s pattern must be a string")
            else:
                try:
                    re.compile(pattern)
                except re.error as e:
                    yield Finding(entry.line, f"{label}'s pattern isn't a valid regex: {e}")
        for key in entry.value:
            if key not in INPUT_KEYS:
                yield Finding(entry.line, f"unknown key {key!r} on {label}", warning=True)


@dataclass(frozen=True)
class _YamlError:
    """An input block whose YAML can't be read."""

    line: int  # file line the YAML problem is on
    problem: str


def _entries(runbook: Runbook) -> Iterator[_Entry]:
    """Every input declaration in file order: the frontmatter's inputs, then each input block."""
    items = runbook.frontmatter.get("inputs")
    if isinstance(items, list):
        for index, item in enumerate(items):
            yield _Entry(item, runbook.lines.get(f"inputs.{index}", 1), f"input {index + 1}", None)
    for block in _all_blocks(runbook):
        if block.kind == "input":
            yield _Entry(_input_block_yaml(block), block.line, "input block", block)


def _input_block_yaml(block: Block) -> Any:
    """The YAML in an input block, or a _YamlError saying where it can't be read."""
    try:
        return yaml.safe_load(block.content)
    except yaml.MarkedYAMLError as e:
        # Marks count from the block's first line, which is the line after its fence.
        line = block.line if e.problem_mark is None else block.line + 1 + e.problem_mark.line
        return _YamlError(line, str(e.problem))


def _upper_snake(name: str) -> str:
    """A valid input name to suggest in place of name."""
    suggestion = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "NAME"
    # Names start with a letter, so give one that starts with a digit something to start with.
    return suggestion if suggestion[0].isalpha() else f"INPUT_{suggestion}"


def _placeholders(runbook: Runbook) -> Iterator[Finding]:
    """Every <NAME> must be a declared, non-secret input that's known by then, and every input should be used."""
    declared = _declared(runbook)
    used: set[str] = set()
    for line, text, prefix in _placeholder_texts(runbook):
        for match in PLACEHOLDER.finditer(text):
            name = match.group(1)
            used.add(name)
            at = line + text.count("\n", 0, match.start())
            entry = declared.get(name)
            if entry is None:
                yield Finding(at, f"{prefix}<{name}> isn't a declared input")
            elif entry.secret:
                yield Finding(
                    at,
                    f"{prefix}<{name}> is a secret, so it's never substituted; "
                    f"use ${name} to read it from the environment",
                )
            elif entry.block is not None and prefix:
                yield Finding(at, f"{prefix}<{name}> comes from an input block, so it isn't known when the run starts")
            elif entry.block is not None and at < entry.block.line:
                yield Finding(at, f"<{name}> is used before its input block on line {entry.block.line}")
    # A run block can also read an input from its environment, e.g. $TOKEN, so any mention of the name counts.
    for block in _all_blocks(runbook):
        if block.kind != "run":
            continue
        for name, entry in declared.items():
            if mention := re.search(rf"\b{re.escape(name)}\b", block.content):
                used.add(name)
                at = block.line + 1 + block.content.count("\n", 0, mention.start())
                if entry.block is not None and at < entry.block.line and f"<{name}>" not in block.content:
                    yield Finding(at, f"${name} is used before its input block on line {entry.block.line}")
    for name, entry in declared.items():
        if name not in used:
            yield Finding(entry.line, f"input {name} is never used", warning=True)


def _declared(runbook: Runbook) -> dict[str, _Entry]:
    """Each declared input name, from the frontmatter or an input block, even if it has other errors.

    Using every named entry, not just the inputs the parser could read, means an input missing its
    description is reported once, rather than again for each placeholder that uses it. A repeated name
    is judged by its first declaration, since the repeat is already an error of its own.
    """
    declared: dict[str, _Entry] = {}
    for entry in _entries(runbook):
        if entry.name is not None and entry.name not in declared:
            declared[entry.name] = entry
    return declared


def _placeholder_texts(runbook: Runbook) -> Iterator[tuple[int, str, str]]:
    """Each text placeholders are substituted into, with the file line its first line is on, and a message prefix."""
    if runbook.output_path is not None:
        yield runbook.lines.get("output_path", 1), runbook.output_path, "output_path: "
    for block in _all_blocks(runbook):
        if block.kind != "input":  # an input block declares an input; nothing is substituted into it
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
