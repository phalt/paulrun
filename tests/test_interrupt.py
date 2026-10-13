"""Tests for pressing Ctrl-C during a run.

In a terminal, Ctrl-C sends SIGINT to every process in the foreground group: paulrun and whatever block
it's running. These tests do the same, starting paulrun in its own process group and signalling the
whole group, so nothing here fakes the signal.
"""

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from paulrun.backends import Interrupted, _kill_tree, stream


def start_in_own_group(command: list[str], **kwargs) -> subprocess.Popen:
    """Start a process as the leader of a new process group, like a job a terminal runs."""
    return subprocess.Popen(command, start_new_session=True, **kwargs)


def press_ctrl_c(process: subprocess.Popen) -> None:
    """Send SIGINT to the process's whole group, as a terminal does for Ctrl-C."""
    os.killpg(process.pid, signal.SIGINT)


def wait_for(path: Path, timeout: float = 10) -> None:
    """Wait until path exists, so a signal is only sent once the block has really started."""
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.02)


# A small program that streams a command's output with stream(), printing each line and then the exit code.
STREAM_DRIVER = textwrap.dedent(
    """\
    import os, sys
    from pathlib import Path

    from paulrun.backends import Interrupted, stream

    try:
        code = stream(
            sys.argv[1:], env=os.environ, cwd=Path.cwd(), output=lambda line: print("line:", line, flush=True)
        )
    except Interrupted as interrupted:
        print("interrupted, exit", interrupted.exit_code, flush=True)
    else:
        print("exit", code, flush=True)
    """
)


def run_stream(command: list[str], tmp_path: Path, *, presses: int) -> list[str]:
    """Stream command with Ctrl-C pressed the given number of times once it's started. Returns the driver's lines."""
    started = tmp_path / "started"
    driver = start_in_own_group(
        [sys.executable, "-c", STREAM_DRIVER, *command], cwd=tmp_path, stdout=subprocess.PIPE, text=True
    )
    wait_for(started)
    for _ in range(presses):
        press_ctrl_c(driver)
        time.sleep(0.3)
    output, _ = driver.communicate(timeout=10)
    return output.splitlines()


def test_stream_returns_the_exit_code_and_passes_each_line():
    """Without an interrupt, stream passes each line on and returns the command's exit code."""
    lines: list[str] = []

    code = stream(["sh", "-c", "echo one; echo two; exit 4"], env=os.environ, cwd=Path.cwd(), output=lines.append)

    assert lines == ["one", "two"]
    assert code == 4


def test_ctrl_c_lets_the_block_finish_stopping_and_keeps_its_output(tmp_path):
    """Ctrl-C reaches the block too. stream waits for it to exit, passes on what it printed, then re-raises."""
    script = "trap 'echo \"cleaning up\"; exit 130' INT; echo before; touch started; while :; do sleep 0.05; done"

    lines = run_stream(["bash", "-c", script], tmp_path, presses=1)

    assert lines == ["line: before", "line: cleaning up", "interrupted, exit 130"]


def test_a_second_ctrl_c_kills_a_block_that_ignores_the_first(tmp_path):
    """A block that ignores Ctrl-C is killed by the second press, so paulrun can't be stuck waiting for it."""
    script = "trap '' INT; echo before; touch started; while :; do sleep 0.05; done"

    lines = run_stream(["bash", "-c", script], tmp_path, presses=2)

    assert lines[0] == "line: before"
    assert lines[-1] == f"interrupted, exit {-signal.SIGKILL}"


@pytest.fixture
def runbook(tmp_path):
    """Write a runbook into tmp_path whose transcript goes to tmp_path / "transcript.md"."""

    def write(body: str) -> Path:
        path = tmp_path / "runbook.md"
        path.write_text("---\ntitle: T\noutput_path: transcript.md\n---\n\n" + textwrap.dedent(body))
        return path

    return write


def run_paulrun(path: Path, *, answers: str, at: str | Path) -> tuple[int, str]:
    """Run paulrun go, typing answers, and press Ctrl-C once it gets to `at`. Returns its exit code and output.

    paulrun is started in the runbook's directory, so the files its blocks make are next to the runbook.
    `at` is either text paulrun prints, such as a prompt, or a file a block creates once it's running.
    Waiting for one of those, not for a length of time, makes sure Ctrl-C lands where the test means.
    """
    paulrun = start_in_own_group(
        [sys.executable, "-c", "from paulrun.cli import cli; cli()", "go", str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "NO_COLOR": "1"},
        cwd=path.parent,
    )
    assert paulrun.stdin is not None and paulrun.stdout is not None  # set because both are pipes
    paulrun.stdin.write(answers.encode())
    paulrun.stdin.flush()
    output = b""
    if isinstance(at, Path):
        wait_for(at)
    else:
        deadline = time.monotonic() + 10
        while at.encode() not in output:
            assert time.monotonic() < deadline, f"paulrun never printed {at!r}: {output!r}"
            # Prompts don't end in a newline, so read whatever has arrived rather than whole lines.
            output += os.read(paulrun.stdout.fileno(), 1024)
    press_ctrl_c(paulrun)
    rest, _ = paulrun.communicate(timeout=10)
    return paulrun.returncode, (output + rest).decode()


def test_go_ctrl_c_during_a_block_records_it_and_finishes_as_interrupted(runbook, tmp_path):
    """The block's output and exit code are kept, later steps don't run, and the run ends as interrupted."""
    path = runbook(
        """\
        ## Slow

        ```sh run
        trap 'echo "stopping cleanly"; exit 130' INT
        echo before
        touch started
        while :; do sleep 0.05; done
        ```

        ## Never reached

        ```sh run
        touch later-ran
        ```
        """
    )

    exit_code, output = run_paulrun(path, answers="y\n", at=tmp_path / "started")

    assert exit_code == 1
    assert "stopping cleanly" in output.splitlines()
    assert 'finished: interrupted at "Slow"' in output.splitlines()
    assert "Traceback" not in output
    assert not (tmp_path / "later-ran").exists()
    transcript = (tmp_path / "transcript.md").read_text()
    assert "before\nstopping cleanly\nexit 130 (" in transcript
    assert transcript.endswith('\n--- finished: interrupted at "Slow"\n')


def test_go_ctrl_c_at_a_confirm_finishes_as_interrupted(runbook, tmp_path):
    """Ctrl-C while paulrun waits at a confirm ends the run there, with no answer recorded."""
    path = runbook(
        """\
        ## First

        ```sh run
        touch started
        ```

        ## Manual

        ```confirm
        Do the manual thing.
        ```
        """
    )

    exit_code, output = run_paulrun(path, answers="y\n", at="Continue? [y/N] ")

    assert exit_code == 1
    assert 'finished: interrupted at "Manual"' in output.splitlines()
    assert "Aborted!" not in output
    transcript = (tmp_path / "transcript.md").read_text()
    assert "confirm:" not in transcript
    assert transcript.endswith('=== Manual ===\n\n--- finished: interrupted at "Manual"\n')


def test_go_ctrl_c_before_starting_writes_no_transcript(runbook, tmp_path):
    """Ctrl-C at the start prompt ends the run before any step, so there's nothing to record."""
    path = runbook("## Only\n\n```sh run\ntouch ran\n```\n")

    exit_code, output = run_paulrun(path, answers="", at="Start? [y/N] ")

    assert exit_code == 1
    assert output.rstrip().endswith("finished: interrupted before starting")
    assert not (tmp_path / "transcript.md").exists()
    assert not (tmp_path / "ran").exists()


def test_interrupted_is_a_keyboard_interrupt():
    """Anything that already handles Ctrl-C as KeyboardInterrupt still handles a block being interrupted."""
    assert issubclass(Interrupted, KeyboardInterrupt)
    assert Interrupted(130).exit_code == 130


def test_stream_waits_for_the_command_to_stop_after_ctrl_c_and_keeps_its_output(tmp_path):
    """In-process view of the first Ctrl-C: the terminal sends SIGINT to the command as well as paulrun.
    stream waits for it to stop, passes on what it prints while stopping, then raises Interrupted."""
    lines: list[str] = []
    script = "trap 'echo stopping; exit 130' INT; echo $$ > pid; echo ready; while :; do sleep 0.05; done"

    def output(line: str) -> None:
        lines.append(line)
        if line == "ready":
            # What the terminal does for Ctrl-C: SIGINT to the command, KeyboardInterrupt in paulrun.
            os.kill(int((tmp_path / "pid").read_text()), signal.SIGINT)
            raise KeyboardInterrupt

    with pytest.raises(Interrupted) as error:
        stream(["bash", "-c", script], env=os.environ, cwd=tmp_path, output=output)

    assert lines == ["ready", "stopping"]
    assert error.value.exit_code == 130


def test_stream_kills_the_command_and_its_children_on_a_second_ctrl_c(tmp_path):
    """In-process view of a second Ctrl-C: stream kills the whole group, so a child holding the output open
    can't keep it waiting."""
    script = "trap '' INT; echo first; sleep 0.2; echo second; sleep 30"
    presses = 0
    started = time.monotonic()

    def output(line: str) -> None:
        nonlocal presses
        presses += 1
        raise KeyboardInterrupt  # both lines are printed while the block ignores Ctrl-C

    with pytest.raises(Interrupted) as error:
        stream(["bash", "-c", script], env=os.environ, cwd=tmp_path, output=output)

    assert presses == 2
    assert error.value.exit_code == -signal.SIGKILL
    assert time.monotonic() - started < 5


def test_stream_ignores_a_command_that_has_already_exited_when_ctrl_c_is_pressed(tmp_path):
    """If the command exits right as Ctrl-C lands, there's nothing to signal, and stream still reports it."""

    def output(line: str) -> None:
        raise KeyboardInterrupt

    with pytest.raises(Interrupted) as error:
        stream(["sh", "-c", "echo last; exit 4"], env=os.environ, cwd=tmp_path, output=output)

    assert error.value.exit_code == 4


def test_a_second_ctrl_c_also_stops_what_the_block_started(tmp_path):
    """A block's own child processes are killed with it on the second press, not left running."""
    script = "trap '' INT; sh -c 'trap \"\" INT; echo $$ > child; while :; do sleep 0.05; done' & touch started; wait"

    run_stream(["bash", "-c", script], tmp_path, presses=2)

    child = int((tmp_path / "child").read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)


def test_killing_a_process_tree_ignores_processes_that_have_already_exited():
    """A process can exit between being found and being signalled; that's not an error."""
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()

    _kill_tree(finished.pid)  # nothing to kill, and nothing raised
