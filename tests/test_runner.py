"""Tests for running a runbook's steps. Blocks really run under bash in tmp_path."""

import textwrap
import time
from pathlib import Path

import pytest

from paulrun import runner
from paulrun.backends import load_backends
from paulrun.runbook import parse


def write_runbook(directory: Path, text: str) -> Path:
    """Write a dedented runbook.md into directory, creating it if needed, and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "runbook.md"
    path.write_text(textwrap.dedent(text))
    return path


def run(path: Path) -> tuple[list[runner.Event], runner.RunFinished]:
    """Run the runbook at path with the installed backends, returning every event sent and the result."""
    events: list[runner.Event] = []
    result = runner.run(parse(path), load_backends(), events.append)
    return events, result


def output(events: list[runner.Event]) -> list[str]:
    """The lines blocks printed, in order."""
    return [event.text for event in events if isinstance(event, runner.OutputLine)]


def test_run_sends_events_for_each_step_and_block_in_order(tmp_path):
    """Each step starts, then each of its blocks starts, prints and finishes, and the run finishes last."""
    path = write_runbook(
        tmp_path,
        """\
        ## First

        ```sh run
        echo one
        ```

        ## Second

        ```sh run
        echo two
        ```
        """,
    )

    events, _ = run(path)

    assert [type(event) for event in events] == [
        runner.StepStarted,
        runner.BlockStarted,
        runner.OutputLine,
        runner.BlockFinished,
        runner.StepStarted,
        runner.BlockStarted,
        runner.OutputLine,
        runner.BlockFinished,
        runner.RunFinished,
    ]
    assert [event.step.name for event in events if isinstance(event, runner.StepStarted)] == ["First", "Second"]
    assert [event.code for event in events if isinstance(event, runner.BlockStarted)] == ["echo one\n", "echo two\n"]
    assert output(events) == ["one", "two"]


def test_run_returns_the_run_finished_event_it_sends_last(tmp_path):
    """The result is the same event the sink got last, so the caller doesn't have to keep track."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\necho hi\n```\n")

    events, result = run(path)

    assert events[-1] is result
    assert result.status == "ok"
    assert result.step is None
    assert result.exit_code is None


def test_run_streams_output_lines_as_they_are_printed(tmp_path):
    """Lines from a slow block reach the sink one at a time, not all together when the block ends."""
    path = write_runbook(
        tmp_path,
        """\
        ## Count slowly

        ```sh run
        for i in 1 2 3; do echo "$i"; sleep 0.2; done
        ```
        """,
    )
    arrivals: list[float] = []

    def sink(event: runner.Event) -> None:
        if isinstance(event, runner.OutputLine):
            arrivals.append(time.monotonic())

    runner.run(parse(path), load_backends(), sink)

    assert len(arrivals) == 3
    assert arrivals[2] - arrivals[0] >= 0.3


def test_run_runs_blocks_in_the_runbook_directory(tmp_path, monkeypatch):
    """Blocks run where the runbook is, even when paulrun is started somewhere else with a relative path."""
    write_runbook(tmp_path / "book", "## Where\n\n```sh run\npwd -P\n```\n")
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")

    events, _ = run(Path("../book/runbook.md"))

    assert output(events) == [str((tmp_path / "book").resolve())]


def test_run_stops_at_the_first_failing_block(tmp_path):
    """Once a block fails, nothing after it runs: not the rest of its step, and not later steps."""
    path = write_runbook(
        tmp_path,
        """\
        ## Fails

        ```sh run
        echo before
        exit 3
        ```

        ```sh run
        touch same-step-ran
        ```

        ## Never reached

        ```sh run
        touch later-step-ran
        ```
        """,
    )

    events, _ = run(path)

    assert output(events) == ["before"]
    assert not (tmp_path / "same-step-ran").exists()
    assert not (tmp_path / "later-step-ran").exists()
    assert [event.step.name for event in events if isinstance(event, runner.StepStarted)] == ["Fails"]


def test_run_result_names_the_failed_step_and_exit_code(tmp_path):
    """A failed run says which step failed and the failing block's exit code."""
    path = write_runbook(
        tmp_path,
        """\
        ## Passes

        ```sh run
        true
        ```

        ## Fails

        ```sh run
        exit 3
        ```
        """,
    )

    _, result = run(path)

    assert result.status == "failed"
    assert result.step is not None
    assert result.step.name == "Fails"
    assert result.exit_code == 3


def test_run_adds_streaming_and_pager_settings_to_block_env(tmp_path, monkeypatch):
    """Python output isn't held back and nothing opens a pager, even if paulrun's environment sets one."""
    monkeypatch.setenv("PAGER", "less")
    path = write_runbook(tmp_path, '## Env\n\n```sh run\necho "$PYTHONUNBUFFERED $GIT_PAGER $PAGER"\n```\n')

    events, _ = run(path)

    assert output(events) == ["1 cat cat"]


def test_run_passes_paulrun_environment_to_blocks(tmp_path, monkeypatch):
    """Blocks see the environment paulrun was started with."""
    monkeypatch.setenv("PAULRUN_TEST_INHERITED", "yes")
    path = write_runbook(tmp_path, '## Env\n\n```sh run\necho "$PAULRUN_TEST_INHERITED"\n```\n')

    events, _ = run(path)

    assert output(events) == ["yes"]


def test_run_records_how_long_blocks_and_the_run_took(tmp_path):
    """Each block's duration covers the time it ran, and the run's duration covers all of them."""
    path = write_runbook(tmp_path, "## Slow\n\n```sh run\nsleep 0.2\n```\n")

    events, result = run(path)

    [finished] = [event for event in events if isinstance(event, runner.BlockFinished)]
    assert finished.exit_code == 0
    assert finished.duration >= 0.2
    assert result.duration >= finished.duration


def test_run_never_runs_docstring_or_confirm_blocks(tmp_path):
    """Only run blocks are executed."""
    path = write_runbook(
        tmp_path,
        """\
        ## Prose only

        ```docstring
        touch docstring-ran
        ```

        ```confirm
        touch confirm-ran
        ```
        """,
    )

    events, result = run(path)

    assert not (tmp_path / "docstring-ran").exists()
    assert not (tmp_path / "confirm-ran").exists()
    assert not [event for event in events if isinstance(event, runner.BlockStarted)]
    assert result.status == "ok"


def test_run_never_runs_blocks_before_the_first_step(tmp_path):
    """A run block before the first ## heading isn't part of any step, so it never runs."""
    path = write_runbook(
        tmp_path,
        """\
        ```sh run
        touch preamble-ran
        ```

        ## Step

        ```sh run
        echo step
        ```
        """,
    )

    events, _ = run(path)

    assert not (tmp_path / "preamble-ran").exists()
    assert output(events) == ["step"]


def test_run_rejects_block_with_no_backend_before_running_anything(tmp_path):
    """A run block nothing can run is an error up front, so earlier steps don't half-run."""
    path = write_runbook(
        tmp_path,
        """\
        ## Runs fine

        ```sh run
        touch first-step-ran
        ```

        ## No backend

        ```cobol run
        DISPLAY 'HELLO'.
        ```
        """,
    )
    events: list[runner.Event] = []

    with pytest.raises(runner.RunnerError) as error:
        runner.run(parse(path), load_backends(), events.append)

    assert str(error.value) == "line 9: no backend runs 'cobol' blocks"
    assert events == []
    assert not (tmp_path / "first-step-ran").exists()
