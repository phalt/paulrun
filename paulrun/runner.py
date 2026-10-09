import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from paulrun.backends import Backend
from paulrun.runbook import Block, Runbook, Step

# Blocks print to a pipe rather than a terminal. Python would hold its output back until it exits,
# and anything that opens a pager would wait for keys nobody can see, so turn both off.
_BLOCK_ENV = {"PYTHONUNBUFFERED": "1", "GIT_PAGER": "cat", "PAGER": "cat"}


@dataclass(frozen=True)
class StepStarted:
    step: Step


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
    status: Literal["ok", "failed"]
    duration: float  # seconds
    step: Step | None = None  # the step that failed
    exit_code: int | None = None  # the failed block's exit code


Event = StepStarted | BlockStarted | OutputLine | BlockFinished | RunFinished


class RunnerError(Exception):
    """The runbook can't be run, e.g. a run block has no backend."""


def run(runbook: Runbook, backends: Mapping[str, Backend], sink: Callable[[Event], None]) -> RunFinished:
    """Run each step's run blocks in order, stopping at the first that fails.

    Every event goes to sink as it happens, ending with the RunFinished event that's also returned.
    Blocks run in the runbook's directory with paulrun's environment.
    """
    for step in runbook.steps:
        for block in step.blocks:
            if block.kind == "run" and block.language not in backends:
                raise RunnerError(f"line {block.line}: no backend runs {block.language!r} blocks")
    env = {**os.environ, **_BLOCK_ENV}
    started = time.monotonic()
    for step in runbook.steps:
        sink(StepStarted(step))
        for block in step.blocks:
            if block.kind != "run":
                continue
            assert block.language is not None  # always set for run blocks
            sink(BlockStarted(block, block.content))
            block_started = time.monotonic()
            exit_code = backends[block.language].run(
                block.content,
                frontmatter=runbook.frontmatter,
                env=env,
                cwd=runbook.path.parent,
                output=lambda line: sink(OutputLine(line)),
            )
            sink(BlockFinished(block, exit_code, time.monotonic() - block_started))
            if exit_code != 0:
                return _finish(sink, RunFinished("failed", time.monotonic() - started, step, exit_code))
    return _finish(sink, RunFinished("ok", time.monotonic() - started))


def _finish(sink: Callable[[Event], None], finished: RunFinished) -> RunFinished:
    sink(finished)
    return finished
