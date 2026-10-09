from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Literal

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token

from paulrun.inputs import Input

BlockKind = Literal["docstring", "confirm", "run"]


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    language: str | None  # set for run blocks only
    content: str
    line: int  # line of the opening fence, counted from the top of the file


@dataclass(frozen=True)
class Step:
    name: str
    line: int
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Runbook:
    """A parsed runbook. Core keys that are missing or the wrong type are None; validation reports them."""

    path: Path
    frontmatter: Mapping[str, Any]
    # The file line each frontmatter key starts on, and "inputs.N" for each item in inputs, for error messages.
    lines: Mapping[str, int]
    title: str | None
    description: str | None
    output_path: str | None
    python: str | None
    inputs: tuple[Input, ...]
    preamble: tuple[Block, ...]  # blocks before the first step, which validation rejects
    steps: tuple[Step, ...]


class RunbookError(Exception):
    """The runbook can't be read: broken frontmatter, or text that isn't UTF-8."""


_MARKDOWN = MarkdownIt("commonmark")


def parse(path: Path) -> Runbook:
    """Parse a runbook into steps and blocks. Only checks what's needed to read it; validation is separate."""
    with path.open("rb") as file:
        frontmatter, lines, offset = _read_frontmatter(file)
        body = "".join(_decode(raw, number) for number, raw in enumerate(file, start=offset + 1))
    preamble: list[Block] = []
    steps: list[tuple[str, int, list[Block]]] = []
    tokens = _MARKDOWN.parse(body)
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2":
            steps.append((tokens[index + 1].content, _line(token, offset), []))
        elif token.type == "fence" and (block := _block(token, offset)):
            (steps[-1][2] if steps else preamble).append(block)
    return Runbook(
        path=path,
        frontmatter=frontmatter,
        lines=lines,
        title=_string(frontmatter.get("title")),
        description=_string(frontmatter.get("description")),
        output_path=_string(frontmatter.get("output_path")),
        python=_string(frontmatter.get("python")),
        inputs=_inputs(frontmatter.get("inputs")),
        preamble=tuple(preamble),
        steps=tuple(Step(name=name, line=line, blocks=tuple(blocks)) for name, line, blocks in steps),
    )


def read_frontmatter(path: Path) -> Mapping[str, Any]:
    """Read only the frontmatter. Nothing after the closing --- is decoded or parsed."""
    with path.open("rb") as file:
        frontmatter, _, _ = _read_frontmatter(file)
    return frontmatter


def _read_frontmatter(file: BinaryIO) -> tuple[Mapping[str, Any], Mapping[str, int], int]:
    """Read the frontmatter at the start of file, leaving file at the start of the body.

    Returns the frontmatter, the line each key starts on, and how many lines it took up. Lines are
    decoded one at a time, so a body that isn't UTF-8 can't break reading the frontmatter.
    """
    if _decode(file.readline(), 1).rstrip() != "---":
        file.seek(0)
        return MappingProxyType({}), MappingProxyType({}), 0
    lines = []
    for number, raw in enumerate(file, start=2):
        line = _decode(raw, number)
        if line.rstrip() == "---":
            text = "".join(lines)
            return _load_yaml(text), _key_lines(text), number
        lines.append(line)
    raise RunbookError("frontmatter has no closing ---")


def _decode(raw: bytes, line: int) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise RunbookError(f"line {line} isn't valid UTF-8") from e


def _load_yaml(text: str) -> Mapping[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        if isinstance(e, yaml.MarkedYAMLError) and e.problem_mark is not None:
            # Marks count from the first line inside the frontmatter, which is line 2 of the file.
            line = e.problem_mark.line + 2
            raise RunbookError(f"frontmatter isn't valid YAML at line {line}: {e.problem}") from e
        raise RunbookError(f"frontmatter isn't valid YAML: {e}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RunbookError("frontmatter must be a YAML mapping")
    return MappingProxyType(data)


def _key_lines(text: str) -> Mapping[str, int]:
    """The file line each top-level key in valid frontmatter YAML starts on, plus "inputs.N" for each input."""
    # Node marks count from the first line inside the frontmatter, which is line 2 of the file.
    node = yaml.compose(text, Loader=yaml.SafeLoader)
    lines: dict[str, int] = {}
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            lines[str(key.value)] = key.start_mark.line + 2
            if key.value == "inputs" and isinstance(value, yaml.SequenceNode):
                for index, item in enumerate(value.value):
                    lines[f"inputs.{index}"] = item.start_mark.line + 2
    return MappingProxyType(lines)


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _inputs(value: Any) -> tuple[Input, ...]:
    """Read the inputs that have a string name and description. Validation reports the rest from the frontmatter."""
    if not isinstance(value, list):
        return ()
    return tuple(
        Input(
            name=entry["name"],
            description=entry["description"],
            pattern=_string(entry.get("pattern")),
            # Anything truthy is secret, so a malformed flag can only hide a value, never leak it.
            secret=bool(entry.get("secret", False)),
        )
        for entry in value
        if isinstance(entry, dict) and isinstance(entry.get("name"), str) and isinstance(entry.get("description"), str)
    )


def _block(token: Token, offset: int) -> Block | None:
    """Turn a fence into a block, or None if it's documentation."""
    match token.info.split():
        case ["docstring", *_]:
            return Block(kind="docstring", language=None, content=token.content, line=_line(token, offset))
        case ["confirm", *_]:
            return Block(kind="confirm", language=None, content=token.content, line=_line(token, offset))
        case [language, "run", *_]:
            return Block(kind="run", language=language, content=token.content, line=_line(token, offset))
    return None


def _line(token: Token, offset: int) -> int:
    """The line in the file where a block-level token starts. Body tokens count from 0 after the frontmatter."""
    assert token.map is not None  # markdown-it always maps block-level tokens
    return offset + token.map[0] + 1
