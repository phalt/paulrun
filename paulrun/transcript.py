from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import TextIO

from paulrun import runner
from paulrun.inputs import substitute
from paulrun.runbook import Runbook


def transcript_path(runbook: Runbook, values: Mapping[str, str], cwd: Path) -> Path | None:
    """Where a run's transcript goes: output_path with plain inputs filled in, from cwd, where paulrun runs."""
    if runbook.output_path is None:
        return None
    return cwd / substitute(runbook.output_path, values)


class TranscriptError(Exception):
    """The transcript file can't be written."""


class Transcript:
    """Appends a plain record of a run to a file, as the run goes. Call it with each of the runner's events.

    The file is opened when the first step starts, so a run that's never started writes nothing. Only
    the text the runner sends is written, and the runner masks secrets in all of it, so no secret can
    reach the file. Use it as a context manager so the file is closed however the run ends.
    """

    def __init__(
        self,
        path: Path | None,
        runbook_name: str,
        clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        runbook: Runbook | None = None,
        cwd: Path | None = None,
    ):
        self.path = path
        self._runbook_name = runbook_name
        self._clock = clock
        self._runbook = runbook
        self._cwd = cwd
        self._file: TextIO | None = None
        self._written = False
        self._inputs: tuple[tuple[str, str], ...] = ()

    @classmethod
    def for_runbook(
        cls, runbook: Runbook, cwd: Path, clock: Callable[[], datetime] = lambda: datetime.now().astimezone()
    ) -> "Transcript":
        """A transcript at the runbook's output_path from cwd, worked out once the run's inputs are known."""
        return cls(None, runbook.path.name, clock, runbook=runbook, cwd=cwd)

    @property
    def written(self) -> bool:
        """Whether anything has been written, which is once the run's first step has started."""
        return self._written

    def __enter__(self) -> "Transcript":
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __call__(self, event: runner.Event) -> None:
        match event:
            case runner.Overview(inputs=inputs):
                self._inputs = inputs
                if self._runbook is not None:
                    assert self._cwd is not None  # given with the runbook, by for_runbook
                    # Secrets are **** here, but they're never placeholders in output_path, which check enforces.
                    self.path = transcript_path(self._runbook, dict(inputs), self._cwd)
            case runner.StepStarted(step=step):
                if self._file is None:
                    self._open()
                self._write("", f"=== {step.name} ===")
            case runner.BlockStarted(code=code):
                self._write(*runner.code_lines(code))
            case runner.OutputLine(text=text):
                self._write(text)
            case runner.BlockFinished(exit_code=exit_code, duration=duration):
                self._write(f"exit {exit_code} ({runner.format_duration(duration)})")
            case runner.BlockSkipped():
                self._write("skipped (--step)")
            case runner.ConfirmAnswered(text=text, yes=yes):
                self._write(f"confirm: {_first_line(text)} -> {'yes' if yes else 'no'}")
            case runner.InputCollected(name=name, value=value):
                self._write(f"input: {name}={value}")
            case runner.RunFinished() if self._file is not None:
                self._write("", f"--- finished: {_finished(event)}")

    def _open(self) -> None:
        """Open the file for appending, after a blank line if it already has a run in it, and write the header."""
        assert self.path is not None  # given, or worked out from the runbook at the overview
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            has_runs = self.path.exists() and self.path.stat().st_size > 0
            # Line buffered, so each line is in the file as soon as it's written.
            self._file = self.path.open("a", encoding="utf-8", buffering=1)
        except OSError as e:
            raise TranscriptError(f"can't write the transcript to {self.path}: {e.strerror}") from e
        self._written = True
        if has_runs:
            self._write("")
        self._write(f"--- paulrun {self._runbook_name} @ {self._clock().isoformat(timespec='seconds')}")
        if self._inputs:
            self._write("--- inputs: " + " ".join(f"{name}={value}" for name, value in self._inputs))

    def _write(self, *lines: str) -> None:
        assert self._file is not None  # opened at the first step, before anything else is written
        try:
            for line in lines:
                self._file.write(line + "\n")
        except OSError as e:
            raise TranscriptError(f"can't write the transcript to {self.path}: {e.strerror}") from e


def _first_line(text: str) -> str:
    """The first line of a confirm's text, with ... after it if there's more."""
    lines = text.strip().splitlines() or [""]
    return lines[0] + (" ..." if len(lines) > 1 else "")


def _finished(event: runner.RunFinished) -> str:
    match event:
        case runner.RunFinished(status="failed", step=step, exit_code=exit_code):
            assert step is not None  # always set when a run fails
            return f'failed at "{step.name}" (exit {exit_code})'
        case runner.RunFinished(status="aborted" | "interrupted" as status, step=step):
            # A transcript is only open once a step has started, so a run that stopped early always has a step.
            assert step is not None
            return f'{status} at "{step.name}"'
        case _:
            return f"ok ({runner.format_duration(event.duration)})"
