import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, assert_never

from rundot import runner
from rundot.runbook import Step


def to_json(event: runner.Event, steps: tuple[Step, ...], at: datetime) -> dict[str, Any]:
    """The object --json prints for an event: its type and when it happened, then its own fields.

    steps are the run's steps, from its overview, to number the step that's started. The runner has already
    masked every secret in the text it sends, so none can reach these fields. Adding a field is fine; removing
    or renaming one breaks whatever reads them.
    """
    head = {"at": at.isoformat(timespec="milliseconds")}
    match event:
        case runner.Overview():
            return {
                "event": "overview",
                **head,
                "title": event.title,
                "directory": str(event.directory),
                "inputs": dict(event.inputs),
                "steps": [step.name for step in event.steps],
                "resuming_at": event.resuming_at,
            }
        case runner.StepStarted(step=step):
            number = [s.line for s in steps].index(step.line) + 1
            return {"event": "step_started", **head, "number": number, "name": step.name}
        case runner.Docstring(block=block, text=text):
            return {"event": "docstring", **head, "line": block.line, "text": text}
        case runner.Confirm(block=block, text=text):
            return {"event": "confirm", **head, "line": block.line, "text": text}
        case runner.ConfirmAnswered(block=block, yes=yes):
            return {"event": "confirm_answered", **head, "line": block.line, "yes": yes}
        case runner.InputBlock(block=block, input=input):
            return {
                "event": "input_block",
                **head,
                "line": block.line,
                "name": input.name,
                "description": input.description,
            }
        case runner.InputCollected(block=block, name=name, value=value):
            return {"event": "input_collected", **head, "line": block.line, "name": name, "value": value}
        case runner.BlockStarted(block=block, code=code):
            return {"event": "block_started", **head, "line": block.line, "language": block.language, "code": code}
        case runner.BlockSkipped(block=block):
            return {"event": "block_skipped", **head, "line": block.line}
        case runner.OutputLine(text=text, stderr=stderr):
            return {"event": "output", **head, "text": text, "stderr": stderr}
        case runner.BlockFinished(block=block, exit_code=exit_code, duration=duration):
            return {
                "event": "block_finished",
                **head,
                "line": block.line,
                "exit_code": exit_code,
                "duration": round(duration, 3),
            }
        case runner.RunFinished():
            return {
                "event": "run_finished",
                **head,
                "status": event.status,
                "step": None if event.step is None else event.step.name,
                "exit_code": event.exit_code,
                "duration": round(event.duration, 3),
                "message": event.message,
            }
        case _:
            assert_never(event)


class JsonLines:
    """Writes each of the runner's events as one line of JSON, for --json. Call it with each event."""

    def __init__(
        self, write: Callable[[str], None], clock: Callable[[], datetime] = lambda: datetime.now().astimezone()
    ):
        """write is given each line, without its newline."""
        self._write = write
        self._clock = clock
        self._steps: tuple[Step, ...] = ()

    def __call__(self, event: runner.Event) -> None:
        if isinstance(event, runner.Overview):
            self._steps = event.steps
        self._write(json.dumps(to_json(event, self._steps, self._clock()), ensure_ascii=False))
