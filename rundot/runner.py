import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from rundot.backends import Backend, Interrupted
from rundot.inputs import MASK, Input, NeedsHumanInput, Prompter, collect, mask, substitute
from rundot.runbook import Block, Runbook, Step

# Blocks print to a pipe rather than a terminal. Python would hold its output back until it exits,
# and anything that opens a pager would wait for keys nobody can see, so turn both off.
_BLOCK_ENV = {"PYTHONUNBUFFERED": "1", "GIT_PAGER": "cat", "PAGER": "cat"}


@dataclass(frozen=True)
class Overview:
    title: str  # the runbook's title, or its file name if it has none
    steps: tuple[Step, ...]
    run_blocks: int
    inputs: tuple[tuple[str, str], ...]  # (name, value) in declared order, with **** for each secret
    directory: Path  # where blocks run, so it's seen before anything starts
    resuming_at: int | None = None  # the index of the step a resumed run starts at; None for a run from the start


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
    stderr: bool = False  # whether the block wrote it to stderr


@dataclass(frozen=True)
class BlockFinished:
    block: Block
    exit_code: int
    duration: float  # seconds


@dataclass(frozen=True)
class RunFinished:
    status: Literal["ok", "failed", "aborted", "interrupted", "needs_human_input", "dry"]
    duration: float  # seconds
    step: Step | None = None  # the step it stopped at; None if the run was never started
    exit_code: int | None = None  # the failed block's exit code
    block: Block | None = None  # the confirm or input block a run that needs human input stopped at
    message: str | None = None  # for needs_human_input, what a person has to do, with secrets masked


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
    cwd: Path,
    dry: bool = False,
    step_by_step: bool = False,
    start: tuple[int, int] | None = None,
    saved: Mapping[str, str] = {},
    ask_to_start: bool = True,
) -> RunFinished:
    """Collect the runbook's inputs, ask to start, then go through each step's blocks in order.

    docstring blocks are sent to sink, confirm blocks wait for a y, and run blocks are run, stopping at
    the first that fails. Any answer but y aborts the run. Every event goes to sink as it happens, ending
    with the RunFinished event that's also returned. Blocks run in cwd, the directory rundot was started
    from, with rundot's environment plus every input, and RUNDOT_RUNBOOK_DIR set to the runbook's
    directory. Plain inputs are substituted into each block's text first. Secret values are masked in
    every text sent to sink: block output, but also the title, step names and block text, in case a
    secret's value is written in the runbook itself.

    With dry, every block is still sent with inputs substituted, but nothing runs, nothing is asked
    except plain inputs, and secrets are never collected.

    With step_by_step, each run block's code is sent and then rundot asks whether to run it, skip it
    or quit. Quitting aborts the run. step_by_step does nothing under dry, since nothing runs.

    Ctrl-C once the run has started finishes it as interrupted, so whatever is listening still gets a
    RunFinished. A block that was running has already stopped and had its output and exit code sent.

    A prompter that raises NeedsHumanInput at a confirm or an input block finishes the run as
    needs_human_input there, with the block and a message saying what a person has to do. Raised anywhere
    else, while collecting the frontmatter inputs or input blocks before start, or at Start? or step_by_step's
    question, it isn't caught, so a caller that can't ask must check inputs first and turn both questions off.

    start is the (step, block) to resume a run that stopped part way at, counting from 0, or None to run from
    the start. Any start resumes, (0, 0) included, since a run can stop at the very first block. Steps
    before it, and blocks before it in its step, are neither sent nor run, though the overview still lists
    every step. A confirm at start was what the run stopped at, so it's answered yes without asking. Input
    blocks before start are still collected, with the frontmatter inputs and without being sent, so later
    blocks have their values. saved holds plain values from the last run, used when the environment doesn't
    set an input and before asking. Secrets are never taken from it. With ask_to_start off, the run starts
    without asking Start?.
    """
    resuming = start is not None
    start_step, start_block = start = start or (0, 0)
    if resuming and not (
        0 <= start_step < len(runbook.steps) and 0 <= start_block < len(runbook.steps[start_step].blocks)
    ):
        raise RunnerError(f"can't start at block {start_block} of step {start_step}: the runbook has no such block")
    run_blocks = [block for step in runbook.steps for block in step.blocks if block.kind == "run"]
    for block in run_blocks:
        if block.language not in backends:
            raise RunnerError(f"line {block.line}: no backend runs {block.language!r} blocks")
    for step in runbook.steps:
        for block in step.blocks:
            if block.kind == "input" and block.input is None:
                raise RunnerError(f"line {block.line}: input block isn't a valid input; run rundot check to see why")
    values = collect(runbook.inputs, os.environ, prompter, skip_secrets=dry, saved=saved)
    secrets = [values[input.name] for input in runbook.inputs if input.secret and not dry]
    plain = {input.name: values[input.name] for input in runbook.inputs if not input.secret}
    skipped = _before(runbook.steps, start)
    # Input blocks the run starts after won't be reached, but later blocks may still use their values. A dry
    # run never collects input blocks, since their values may not exist yet.
    for block in [] if dry else skipped:
        if block.input is not None:
            value = collect([block.input], os.environ, prompter, saved=saved)[block.input.name]
            values[block.input.name] = value
            if block.input.secret:
                secrets.append(value)
            else:
                plain[block.input.name] = value
    # A runbook keeps files next to itself by reading them from $RUNDOT_RUNBOOK_DIR, since blocks run elsewhere.
    env = {**os.environ, **_BLOCK_ENV, "RUNDOT_RUNBOOK_DIR": str(runbook.path.parent.resolve()), **values}
    shown = tuple((input.name, MASK if input.secret else values[input.name]) for input in runbook.inputs)
    # Steps keep their blocks as written, so blocks still run as written; only the names sent are masked.
    steps = tuple(replace(step, name=mask(step.name, secrets)) for step in runbook.steps)
    to_run = len(run_blocks) - len([block for block in skipped if block.kind == "run"])
    resuming_at = start_step if resuming else None
    sink(Overview(mask(runbook.title or runbook.path.name, secrets), steps, to_run, shown, cwd, resuming_at))
    try:
        if not dry and ask_to_start and not _yes(prompter.confirm("Start? [y/N]")):
            return _finish(sink, RunFinished("aborted", 0.0))
    except KeyboardInterrupt:
        return _finish(sink, RunFinished("interrupted", 0.0))
    return _steps(
        runbook, backends, sink, prompter, steps, plain, secrets, env, cwd, dry, step_by_step, start, resuming, saved
    )


def _before(steps: tuple[Step, ...], start: tuple[int, int]) -> list[Block]:
    """Every block that comes before start, in order."""
    start_step, start_block = start
    return [block for step in steps[:start_step] for block in step.blocks] + [
        block for step in steps[start_step : start_step + 1] for block in step.blocks[:start_block]
    ]


def _steps(
    runbook: Runbook,
    backends: Mapping[str, Backend],
    sink: Callable[[Event], None],
    prompter: Prompter,
    steps: tuple[Step, ...],
    plain: dict[str, str],
    secrets: list[str],
    env: dict[str, str],
    cwd: Path,
    dry: bool,
    step_by_step: bool,
    start: tuple[int, int],
    resuming: bool,
    saved: Mapping[str, str],
) -> RunFinished:
    """Go through each step's blocks in order from start, finishing the run as interrupted at the step Ctrl-C
    arrives in.

    plain, secrets and env grow as input blocks are answered, so every later block sees their values.
    """
    started = time.monotonic()
    start_step, start_block = start
    for index, step in enumerate(steps[start_step:], start_step):
        first = start_block if index == start_step else 0
        resume_at = first if index == start_step and resuming else None
        try:
            finished = _step(
                runbook,
                backends,
                sink,
                prompter,
                step,
                plain,
                secrets,
                env,
                cwd,
                started,
                dry,
                step_by_step,
                first,
                resume_at,
                saved,
            )
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
    cwd: Path,
    started: float,
    dry: bool,
    step_by_step: bool,
    first: int,
    resume_at: int | None,
    saved: Mapping[str, str],
) -> RunFinished | None:
    """Go through one step's blocks from the one at index first. Returns how the run finished if it stops here,
    or None to carry on.

    resume_at is the index of the block a stopped run resumes at, if it's in this step. A confirm there is
    what the run stopped at, so it counts as answered yes.
    """
    sink(StepStarted(step))
    for index, block in enumerate(step.blocks[first:], first):
        text = mask(substitute(block.content, plain), secrets)
        if block.kind == "docstring":
            sink(Docstring(block, text))
            continue
        if block.kind == "confirm":
            sink(Confirm(block, text))
            if dry:
                continue
            try:
                yes = index == resume_at or _yes(prompter.confirm("Continue? [y/N]"))
            except NeedsHumanInput:
                message = f"{_first_line(text)} Run again once it's done."
                return _finish(sink, _needs_human_input(started, step, block, message))
            sink(ConfirmAnswered(block, text, yes))
            if not yes:
                return _finish(sink, RunFinished("aborted", time.monotonic() - started, step))
            continue
        if block.kind == "input":
            assert block.input is not None  # checked before the run started
            sink(InputBlock(block, block.input))
            if dry:  # the value may not exist yet, so later blocks show <NAME> as written
                continue
            try:
                value = collect([block.input], os.environ, prompter, saved=saved)[block.input.name]
            except NeedsHumanInput:
                message = f"set {block.input.name} ({block.input.description}) and run again."
                return _finish(sink, _needs_human_input(started, step, block, message))
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
                cwd=cwd,
                output=lambda line, *, stderr=False: sink(OutputLine(mask(line, secrets), stderr)),
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


def _needs_human_input(started: float, step: Step, block: Block, message: str) -> RunFinished:
    return RunFinished("needs_human_input", time.monotonic() - started, step, block=block, message=message)


def _first_line(text: str) -> str:
    """The first line of a confirm's text, stripped."""
    return (text.strip().splitlines() or [""])[0]


def _finish(sink: Callable[[Event], None], finished: RunFinished) -> RunFinished:
    sink(finished)
    return finished
