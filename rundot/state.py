import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, get_args

from rundot import runner
from rundot.runbook import Runbook, Step

VERSION = 1

Stopped = Literal["failed", "aborted", "interrupted", "needs_human_input", "running"]


class StateError(Exception):
    """A run's state can't be saved or deleted."""


def state_dir(env: Mapping[str, str]) -> Path:
    """Where runs are saved: $XDG_STATE_HOME/rundot/runs, or ~/.local/state/rundot/runs if it's unset or empty."""
    # An empty variable counts as unset, as it does for the library and inputs.
    base = Path(value).expanduser() if (value := env.get("XDG_STATE_HOME")) else Path.home() / ".local" / "state"
    return base / "rundot" / "runs"


def key(runbook: Path, cwd: Path) -> str:
    """What a run is saved under: its runbook and the directory its blocks run in, both resolved.

    So a symlink or .. can't split one run's state in two or let two runs share one.
    """
    return hashlib.sha256(f"{runbook.resolve()}\n{cwd.resolve()}".encode()).hexdigest()[:16]


def state_path(env: Mapping[str, str], runbook: Path, cwd: Path) -> Path:
    """The file a run of runbook in cwd is saved in."""
    return state_dir(env) / f"{key(runbook, cwd)}.json"


def step_hash(step: Step) -> str:
    """The SHA-256 of a step's name and each block's kind, language and content, to tell when it's changed.

    Lines aren't included, so editing an earlier step doesn't change the steps after it.
    """
    parts = [step.name, [[block.kind, block.language, block.content] for block in step.blocks]]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


@dataclass(frozen=True)
class RunState:
    """Where a run stopped, saved so the next run can resume there. Never holds a secret's value."""

    runbook: str  # the resolved runbook path
    directory: str  # the resolved directory blocks run in
    started_at: str  # ISO 8601, when the run that saved this started
    stopped: Stopped  # how it stopped; running if it was still going when this was saved
    step: int  # the index of the step to resume at
    block: int  # the index of the block in it to start at: 0, unless it stopped for human input
    steps: tuple[tuple[str, str], ...]  # (name, step_hash) of every step, to warn if the runbook has changed
    inputs: Mapping[str, str]  # plain values only
    exit_code: int | None = None  # the failed block's exit code, for a run that failed

    @classmethod
    def load(cls, path: Path, warn: Callable[[str], None]) -> "RunState | None":
        """The run saved at path, or None if there isn't one.

        A file that can't be read, isn't a saved run or is another version is treated as none, after
        warn says why, so a broken file never stops a run.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as e:
            warn(f"ignoring the saved run at {path}: it can't be read ({e})")
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            warn(f"ignoring the saved run at {path}: it isn't valid JSON")
            return None
        if isinstance(data, dict) and "version" in data and data["version"] != VERSION:
            warn(f"ignoring the saved run at {path}: it is version {data['version']}, not {VERSION}")
            return None
        try:
            return _from_json(data)
        except ValueError:
            warn(f"ignoring the saved run at {path}: it isn't a saved run")
            return None

    def save(self, path: Path) -> None:
        """Write this to path, readable only by its owner.

        It's written to a temporary file that's then renamed over path, so a run killed while saving leaves
        either the old file or the new one, never half of one.
        """
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # mkstemp creates the file readable and writable by its owner only.
            descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        except OSError as e:
            raise StateError(f"can't save the run's state to {path}: {e.strerror}") from e
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(self._to_json(), file, indent=2)
                file.write("\n")
            os.replace(temporary, path)
        except OSError as e:
            Path(temporary).unlink(missing_ok=True)
            raise StateError(f"can't save the run's state to {path}: {e.strerror}") from e

    @staticmethod
    def delete(path: Path) -> None:
        """Remove the run saved at path, if there is one."""
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            raise StateError(f"can't delete the run's state at {path}: {e.strerror}") from e

    def _to_json(self) -> dict[str, Any]:
        return {
            "version": VERSION,
            "runbook": self.runbook,
            "directory": self.directory,
            "started_at": self.started_at,
            "stopped": self.stopped,
            "step": self.step,
            "block": self.block,
            "steps": [{"name": name, "hash": hash} for name, hash in self.steps],
            "inputs": dict(self.inputs),
            "exit_code": self.exit_code,
        }


def _from_json(data: Any) -> RunState:
    """The RunState data holds, or ValueError if it doesn't hold one."""
    if not isinstance(data, dict):
        raise ValueError
    strings = [data.get(name) for name in ("runbook", "directory", "started_at")]
    numbers = [data.get(name) for name in ("step", "block")]
    steps = data.get("steps")
    inputs = data.get("inputs")
    exit_code = data.get("exit_code")
    if (
        not all(isinstance(value, str) for value in strings)
        # bool is an int in Python, but true isn't a step.
        or not all(type(value) is int and value >= 0 for value in numbers)
        or data.get("stopped") not in get_args(Stopped)
        or not isinstance(steps, list)
        or not all(isinstance(step, dict) and _strings(step.get("name"), step.get("hash")) for step in steps)
        or not isinstance(inputs, dict)
        or not _strings(*inputs.values())
        or not (exit_code is None or type(exit_code) is int)
    ):
        raise ValueError
    return RunState(
        runbook=data["runbook"],
        directory=data["directory"],
        started_at=data["started_at"],
        stopped=data["stopped"],
        step=data["step"],
        block=data["block"],
        steps=tuple((step["name"], step["hash"]) for step in steps),
        inputs=inputs,
        exit_code=exit_code,
    )


def _strings(*values: Any) -> bool:
    return all(isinstance(value, str) for value in values)


class StateRecorder:
    """Saves where a run has got to as it goes, so it can be resumed. Call it with each of the runner's events.

    Nothing is saved until the first step starts, so a run stopped at Start? leaves any saved run as it
    was. Don't listen to a dry run: its steps start too, but dry runs never read or write state. It's saved
    again as each step starts, and as each plain input block is answered. A run that finishes ok deletes it.
    Only plain values are saved, and step names as the runner sends them, with secrets masked, so no secret's
    value can reach the file.
    """

    def __init__(
        self,
        path: Path,
        runbook: Runbook,
        cwd: Path,
        clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        saved: Mapping[str, str] = {},
    ):
        """saved holds the plain values the run was given from the last one, which are carried forward."""
        self.path = path
        self._runbook = runbook
        self._cwd = cwd
        self._clock = clock
        self._secrets = {input.name for input in runbook.inputs if input.secret} | {
            block.input.name
            for step in runbook.steps
            for block in step.blocks
            if block.input is not None and block.input.secret
        }
        self._saved = {name: value for name, value in saved.items() if name not in self._secrets}
        # The index of each step by its line, since the steps in events have secrets masked in their names.
        self._indexes = {step.line: index for index, step in enumerate(runbook.steps)}
        self._state: RunState | None = None
        self._steps: tuple[tuple[str, str], ...] = ()
        self._started_at = ""

    def __call__(self, event: runner.Event) -> None:
        match event:
            case runner.Overview(steps=steps, inputs=inputs):
                self._started_at = self._clock().isoformat(timespec="seconds")
                hashes = [step_hash(step) for step in self._runbook.steps]
                self._steps = tuple((step.name, hash) for step, hash in zip(steps, hashes, strict=True))
                plain = {name: value for name, value in inputs if name not in self._secrets}
                self._saved = self._saved | plain
            case runner.StepStarted(step=step):
                self._save(self._new("running", self._indexes[step.line], 0))
            case runner.InputCollected(block=block, name=name, value=value) if self._state is not None:
                assert block.input is not None  # the runner only collects valid input blocks
                if not block.input.secret:
                    self._save(replace(self._state, inputs={**self._state.inputs, name: value}))
            case runner.RunFinished(status="ok") if self._state is not None:
                RunState.delete(self.path)
            case runner.RunFinished(
                status="failed" | "aborted" | "interrupted" | "needs_human_input" as status,
                step=step,
                block=block,
                exit_code=exit_code,
            ) if self._state is not None and step is not None:
                index = self._indexes[step.line]
                at = self._runbook.steps[index].blocks.index(block) if block is not None else 0
                self._save(replace(self._state, stopped=status, step=index, block=at, exit_code=exit_code))

    def _new(self, stopped: Stopped, step: int, block: int) -> RunState:
        return RunState(
            runbook=str(self._runbook.path.resolve()),
            directory=str(self._cwd.resolve()),
            started_at=self._started_at,
            stopped=stopped,
            step=step,
            block=block,
            steps=self._steps,
            inputs=self._state.inputs if self._state is not None else self._saved,
        )

    def _save(self, saved: RunState) -> None:
        saved.save(self.path)
        self._state = saved
