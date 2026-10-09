import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from paulrun.backends import Backend
from paulrun.inputs import Prompter, collect, mask, substitute
from paulrun.runbook import Block, Runbook, Step

# Blocks print to a pipe rather than a terminal. Python would hold its output back until it exits,
# and anything that opens a pager would wait for keys nobody can see, so turn both off.
_BLOCK_ENV = {"PYTHONUNBUFFERED": "1", "GIT_PAGER": "cat", "PAGER": "cat"}


@dataclass(frozen=True)
class Overview:
    title: str  # the runbook's title, or its file name if it has none
    steps: tuple[Step, ...]
    run_blocks: int


@dataclass(frozen=True)
class StepStarted:
    step: Step


@dataclass(frozen=True)
class Docstring:
    block: Block
    text: str  # with plain inputs substituted


@dataclass(frozen=True)
class Confirm:
    block: Block
    text: str  # with plain inputs substituted


@dataclass(frozen=True)
class BlockStarted:
    block: Block
    code: str  # exactly what the backend is given to run


@dataclass(frozen=True)
class OutputLine:
    text: str  # one line the block printed, without its newline


@dataclass(frozen=True)
class BlockFinished:
    block: Block
    exit_code: int
    duration: float  # seconds


@dataclass(frozen=True)
class RunFinished:
    status: Literal["ok", "failed", "aborted"]
    duration: float  # seconds
    step: Step | None = None  # the step that failed or was aborted; None if the run was never started
    exit_code: int | None = None  # the failed block's exit code


Event = Overview | StepStarted | Docstring | Confirm | BlockStarted | OutputLine | BlockFinished | RunFinished


class RunnerError(Exception):
    """The runbook can't be run, e.g. a run block has no backend."""


def run(
    runbook: Runbook, backends: Mapping[str, Backend], sink: Callable[[Event], None], prompter: Prompter
) -> RunFinished:
    """Collect the runbook's inputs, ask to start, then go through each step's blocks in order.

    docstring blocks are sent to sink, confirm blocks wait for a y, and run blocks are run, stopping at
    the first that fails. Any answer but y aborts the run. Every event goes to sink as it happens, ending
    with the RunFinished event that's also returned. Blocks run in the runbook's directory with paulrun's
    environment plus every input. Plain inputs are substituted into each block's text first, and secret
    values are masked in block output.
    """
    run_blocks = [block for step in runbook.steps for block in step.blocks if block.kind == "run"]
    for block in run_blocks:
        if block.language not in backends:
            raise RunnerError(f"line {block.line}: no backend runs {block.language!r} blocks")
    values = collect(runbook.inputs, os.environ, prompter)
    secrets = [values[input.name] for input in runbook.inputs if input.secret]
    plain = {input.name: values[input.name] for input in runbook.inputs if not input.secret}
    env = {**os.environ, **_BLOCK_ENV, **values}
    sink(Overview(runbook.title or runbook.path.name, runbook.steps, len(run_blocks)))
    if not _yes(prompter.confirm("Start? [y/N]")):
        return _finish(sink, RunFinished("aborted", 0.0))
    started = time.monotonic()
    for step in runbook.steps:
        sink(StepStarted(step))
        for block in step.blocks:
            if block.kind == "docstring":
                sink(Docstring(block, substitute(block.content, plain)))
                continue
            if block.kind == "confirm":
                sink(Confirm(block, substitute(block.content, plain)))
                if not _yes(prompter.confirm("Continue? [y/N]")):
                    return _finish(sink, RunFinished("aborted", time.monotonic() - started, step))
                continue
            assert block.language is not None  # always set for run blocks
            code = substitute(block.content, plain)
            sink(BlockStarted(block, code))
            block_started = time.monotonic()
            exit_code = backends[block.language].run(
                code,
                frontmatter=runbook.frontmatter,
                env=env,
                cwd=runbook.path.parent,
                output=lambda line: sink(OutputLine(mask(line, secrets))),
            )
            sink(BlockFinished(block, exit_code, time.monotonic() - block_started))
            if exit_code != 0:
                return _finish(sink, RunFinished("failed", time.monotonic() - started, step, exit_code))
    return _finish(sink, RunFinished("ok", time.monotonic() - started))


def _yes(answer: str) -> bool:
    return answer.strip() == "y"


def _finish(sink: Callable[[Event], None], finished: RunFinished) -> RunFinished:
    sink(finished)
    return finished
