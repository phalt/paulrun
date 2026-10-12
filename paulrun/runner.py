import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Literal

from paulrun.backends import Backend, Interrupted
from paulrun.inputs import MASK, Input, Prompter, collect, mask, substitute
from paulrun.runbook import Block, Runbook, Step

# Blocks print to a pipe rather than a terminal. Python would hold its output back until it exits,
# and anything that opens a pager would wait for keys nobody can see, so turn both off.
_BLOCK_ENV = {"PYTHONUNBUFFERED": "1", "GIT_PAGER": "cat", "PAGER": "cat"}


@dataclass(frozen=True)
class Overview:
    title: str  # the runbook's title, or its file name if it has none
    steps: tuple[Step, ...]
    run_blocks: int
    inputs: tuple[tuple[str, str], ...]  # (name, value) in declared order, with **** for each secret


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
class ConfirmAnswered:
    block: Block
    text: str  # the confirm's text, as in Confirm
    yes: bool  # whether it was answered y


@dataclass(frozen=True)
class InputBlock:
    block: Block
    input: Input  # what the block asks for; sent as the run reaches it, before asking


@dataclass(frozen=True)
class InputCollected:
    block: Block
    name: str
    value: str  # the value given, or **** for a secret


@dataclass(frozen=True)
class BlockStarted:
    block: Block
    code: str  # the code with plain inputs substituted, as the backend runs it but with secret values masked


@dataclass(frozen=True)
class BlockSkipped:
    block: Block  # a run block skipped under step_by_step


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
    status: Literal["ok", "failed", "aborted", "interrupted", "dry"]
    duration: float  # seconds
    step: Step | None = None  # the step it stopped at; None if the run was never started
    exit_code: int | None = None  # the failed block's exit code


Event = (
    Overview
    | StepStarted
    | Docstring
    | Confirm
    | ConfirmAnswered
    | InputBlock
    | InputCollected
    | BlockStarted
    | BlockSkipped
    | OutputLine
    | BlockFinished
    | RunFinished
)

STEP_QUESTION = "Run this block? [y]es / [s]kip / [q]uit"


class RunnerError(Exception):
    """The runbook can't be run, e.g. a run block has no backend."""


def run(
    runbook: Runbook,
    backends: Mapping[str, Backend],
    sink: Callable[[Event], None],
    prompter: Prompter,
    *,
    dry: bool = False,
    step_by_step: bool = False,
) -> RunFinished:
    """Collect the runbook's inputs, ask to start, then go through each step's blocks in order.

    docstring blocks are sent to sink, confirm blocks wait for a y, and run blocks are run, stopping at
    the first that fails. Any answer but y aborts the run. Every event goes to sink as it happens, ending
    with the RunFinished event that's also returned. Blocks run in the runbook's directory with paulrun's
    environment plus every input. Plain inputs are substituted into each block's text first. Secret
    values are masked in every text sent to sink: block output, but also the title, step names and block
    text, in case a secret's value is written in the runbook itself.

    With dry, every block is still sent with inputs substituted, but nothing runs, nothing is asked
    except plain inputs, and secrets are never collected.

    With step_by_step, each run block's code is sent and then paulrun asks whether to run it, skip it
    or quit. Quitting aborts the run. step_by_step does nothing under dry, since nothing runs.

    Ctrl-C once the run has started finishes it as interrupted, so whatever is listening still gets a
    RunFinished. A block that was running has already stopped and had its output and exit code sent.
    """
    run_blocks = [block for step in runbook.steps for block in step.blocks if block.kind == "run"]
    for block in run_blocks:
        if block.language not in backends:
            raise RunnerError(f"line {block.line}: no backend runs {block.language!r} blocks")
    for step in runbook.steps:
        for block in step.blocks:
            if block.kind == "input" and block.input is None:
                raise RunnerError(f"line {block.line}: input block isn't a valid input; run paulrun check to see why")
    values = collect(runbook.inputs, os.environ, prompter, skip_secrets=dry)
    secrets = [values[input.name] for input in runbook.inputs if input.secret and not dry]
    plain = {input.name: values[input.name] for input in runbook.inputs if not input.secret}
    env = {**os.environ, **_BLOCK_ENV, **values}
    shown = tuple((input.name, MASK if input.secret else values[input.name]) for input in runbook.inputs)
    # Steps keep their blocks as written, so blocks still run as written; only the names sent are masked.
    steps = tuple(replace(step, name=mask(step.name, secrets)) for step in runbook.steps)
    sink(Overview(mask(runbook.title or runbook.path.name, secrets), steps, len(run_blocks), shown))
    try:
        if not dry and not _yes(prompter.confirm("Start? [y/N]")):
            return _finish(sink, RunFinished("aborted", 0.0))
    except KeyboardInterrupt:
        return _finish(sink, RunFinished("interrupted", 0.0))
    return _steps(runbook, backends, sink, prompter, steps, plain, secrets, env, dry, step_by_step)


def _steps(
    runbook: Runbook,
    backends: Mapping[str, Backend],
    sink: Callable[[Event], None],
    prompter: Prompter,
    steps: tuple[Step, ...],
    plain: dict[str, str],
    secrets: list[str],
    env: dict[str, str],
    dry: bool,
    step_by_step: bool,
) -> RunFinished:
    """Go through each step's blocks in order, finishing the run as interrupted at the step Ctrl-C arrives in.

    plain, secrets and env grow as input blocks are answered, so every later block sees their values.
    """
    started = time.monotonic()
    for step in steps:
        try:
            finished = _step(runbook, backends, sink, prompter, step, plain, secrets, env, started, dry, step_by_step)
        except KeyboardInterrupt:
            # A block that was running has already stopped and had its output and exit code sent.
            return _finish(sink, RunFinished("interrupted", time.monotonic() - started, step))
        if finished is not None:
            return finished
    return _finish(sink, RunFinished("dry" if dry else "ok", time.monotonic() - started))


def _step(
    runbook: Runbook,
    backends: Mapping[str, Backend],
    sink: Callable[[Event], None],
    prompter: Prompter,
    step: Step,
    plain: dict[str, str],
    secrets: list[str],
    env: dict[str, str],
    started: float,
    dry: bool,
    step_by_step: bool,
) -> RunFinished | None:
    """Go through one step's blocks. Returns how the run finished if it stops here, or None to carry on."""
    sink(StepStarted(step))
    for block in step.blocks:
        text = mask(substitute(block.content, plain), secrets)
        if block.kind == "docstring":
            sink(Docstring(block, text))
            continue
        if block.kind == "confirm":
            sink(Confirm(block, text))
            if dry:
                continue
            yes = _yes(prompter.confirm("Continue? [y/N]"))
            sink(ConfirmAnswered(block, text, yes))
            if not yes:
                return _finish(sink, RunFinished("aborted", time.monotonic() - started, step))
            continue
        if block.kind == "input":
            assert block.input is not None  # checked before the run started
            sink(InputBlock(block, block.input))
            if dry:  # the value may not exist yet, so later blocks show <NAME> as written
                continue
            value = collect([block.input], os.environ, prompter)[block.input.name]
            env[block.input.name] = value
            if block.input.secret:
                secrets.append(value)
            else:
                plain[block.input.name] = value
            sink(InputCollected(block, block.input.name, MASK if block.input.secret else value))
            continue
        assert block.language is not None  # always set for run blocks
        code = substitute(block.content, plain)
        sink(BlockStarted(block, text))
        if dry:
            continue
        if step_by_step:
            answer = _step_answer(prompter)
            if answer == "s":
                sink(BlockSkipped(block))
                continue
            if answer == "q":
                return _finish(sink, RunFinished("aborted", time.monotonic() - started, step))
        block_started = time.monotonic()
        try:
            exit_code = backends[block.language].run(
                code,
                frontmatter=runbook.frontmatter,
                env=env,
                cwd=runbook.path.parent,
                output=lambda line: sink(OutputLine(mask(line, secrets))),
            )
        except Interrupted as interrupted:
            # The block has stopped. Record how it ended before the run finishes as interrupted.
            sink(BlockFinished(block, interrupted.exit_code, time.monotonic() - block_started))
            raise
        sink(BlockFinished(block, exit_code, time.monotonic() - block_started))
        if exit_code != 0:
            return _finish(sink, RunFinished("failed", time.monotonic() - started, step, exit_code))
    return None


def code_lines(code: str) -> list[str]:
    """A block's code as it's shown: each line indented by four spaces, so it stands apart from its output.

    Blank lines stay empty, so a transcript has no trailing whitespace.
    """
    return [f"    {line}" if line else "" for line in code.splitlines()]


def format_duration(seconds: float) -> str:
    """Tenths of a second under a minute, e.g. 4.2s, then minutes and seconds, e.g. 3m12s."""
    if round(seconds, 1) < 60:
        return f"{seconds:.1f}s"
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes}m{seconds:02d}s"


def _yes(answer: str) -> bool:
    return answer.strip() == "y"


def _step_answer(prompter: Prompter) -> str:
    """Ask whether to run a block until the answer is y, s or q. With three choices, none is a safe default."""
    while (answer := prompter.confirm(STEP_QUESTION).strip()) not in ("y", "s", "q"):
        pass
    return answer


def _finish(sink: Callable[[Event], None], finished: RunFinished) -> RunFinished:
    sink(finished)
    return finished
