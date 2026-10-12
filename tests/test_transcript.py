"""Tests for writing a run's transcript to output_path."""

import re
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from paulrun import runner
from paulrun.backends import load_backends
from paulrun.inputs import Input
from paulrun.runbook import parse
from paulrun.transcript import Transcript, TranscriptError, transcript_path

# A fixed time for run headers, so transcripts can be compared exactly.
STARTED = datetime(2026, 10, 7, 10, 2, 13, tzinfo=timezone(timedelta(hours=1)))


class FakePrompter:
    """Answers questions from replies in order, then y. Fails the test if asked for an input."""

    def __init__(self, replies: list[str] | None = None):
        self.replies = list(replies or [])

    def ask(self, input: Input, problem: str | None) -> str:
        raise AssertionError(f"unexpected prompt for {input.name}")

    def confirm(self, question: str) -> str:
        return self.replies.pop(0) if self.replies else "y"


def write_runbook(directory: Path, text: str, name: str = "PUBLISHING.md") -> Path:
    """Write a dedented runbook into directory and return its path."""
    path = directory / name
    path.write_text(textwrap.dedent(text))
    return path


def run_with_transcript(
    path: Path, output: Path, replies: list[str] | None = None, *, step_by_step: bool = False
) -> runner.RunFinished:
    """Run a runbook with every event going to a transcript at output, as go does."""
    transcript = Transcript(output, path.name, clock=lambda: STARTED)
    with transcript:
        return runner.run(parse(path), load_backends(), transcript, FakePrompter(replies), step_by_step=step_by_step)


def without_durations(text: str) -> str:
    """Replace every duration with Xs, since how long blocks take varies."""
    return re.sub(r"\((\d+m)?\d+(\.\d)?s\)", "(Xs)", text)


RELEASE = """\
---
title: Release
inputs:
  - name: VERSION
    description: The version
  - name: TOKEN
    description: A token
    secret: true
---

## Build

```docstring
Docstrings aren't part of the transcript.
```

```sh run
echo "Building <VERSION>"
echo "warning on stderr" >&2
```

## Tag

```sh run
echo "Tagged <VERSION>"
```

```confirm
Create a release from tag <VERSION>.
Then check it on GitHub.
```

## Publish

```sh run
echo "Publishing with $TOKEN"
```
"""


def test_transcript_records_a_run_in_the_spec_format(tmp_path, monkeypatch):
    """The header, each step, each block's code, output and exit, each confirm answer, and how it finished."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(tmp_path, RELEASE)
    output = tmp_path / "transcript.md"

    run_with_transcript(path, output)

    assert without_durations(output.read_text()) == textwrap.dedent(
        """\
        --- paulrun PUBLISHING.md @ 2026-10-07T10:02:13+01:00
        --- inputs: VERSION=1.2.0 TOKEN=****

        === Build ===
            echo "Building 1.2.0"
            echo "warning on stderr" >&2
        Building 1.2.0
        warning on stderr
        exit 0 (Xs)

        === Tag ===
            echo "Tagged 1.2.0"
        Tagged 1.2.0
        exit 0 (Xs)
        confirm: Create a release from tag 1.2.0. ... -> yes

        === Publish ===
            echo "Publishing with $TOKEN"
        Publishing with ****
        exit 0 (Xs)

        --- finished: ok (Xs)
        """
    )


def test_transcript_appends_each_run_to_the_same_file(tmp_path, monkeypatch):
    """A second run is added after the first, with a blank line between, so a failed attempt and its rerun are kept."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(tmp_path, RELEASE)
    output = tmp_path / "transcript.md"

    run_with_transcript(path, output)
    first = without_durations(output.read_text())
    run_with_transcript(path, output)

    assert without_durations(output.read_text()) == first + "\n" + first


def test_transcript_never_contains_a_secret_value(tmp_path, monkeypatch):
    """A secret printed by a block, in code, or anywhere else in the runbook is written as ****."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Leaky s3cret
        inputs:
          - name: TOKEN
            description: A token
            secret: true
        ---

        ## Leak s3cret

        ```confirm
        Paste s3cret somewhere.
        ```

        ```sh run
        echo "$TOKEN"
        echo "token=$TOKEN and again $TOKEN" >&2
        test "$TOKEN" = s3cret
        ```
        """,
    )
    output = tmp_path / "transcript.md"

    run_with_transcript(path, output)

    text = output.read_text()
    assert "s3cret" not in text
    assert "token=**** and again ****" in text


def test_transcript_records_a_failed_run(tmp_path):
    """A failed block's exit code is recorded, and the run finishes as failed at its step. Later steps aren't there."""
    path = write_runbook(
        tmp_path, "## Passes\n\n```sh run\ntrue\n```\n\n## Fails\n\n```sh run\nexit 3\n```\n\n## Never\n"
    )
    output = tmp_path / "transcript.md"

    run_with_transcript(path, output)

    text = without_durations(output.read_text())
    assert text.endswith('=== Fails ===\n    exit 3\nexit 3 (Xs)\n\n--- finished: failed at "Fails" (exit 3)\n')
    assert "=== Never ===" not in text


def test_transcript_records_a_confirm_answered_no_and_the_abort(tmp_path):
    """A confirm not answered y is recorded as no, and the run finishes as aborted at its step."""
    path = write_runbook(tmp_path, "## Manual\n\n```confirm\nDo the manual thing.\n```\n\n```sh run\ntouch ran\n```\n")
    output = tmp_path / "transcript.md"

    run_with_transcript(path, output, replies=["y", "n"])

    assert output.read_text().endswith(
        '=== Manual ===\nconfirm: Do the manual thing. -> no\n\n--- finished: aborted at "Manual"\n'
    )


def test_transcript_records_skipped_blocks_and_a_quit(tmp_path):
    """Under --step, a skipped block is recorded after its code, and quitting finishes the run as aborted."""
    path = write_runbook(tmp_path, "## One\n\n```sh run\necho one\n```\n\n## Two\n\n```sh run\necho two\n```\n")
    output = tmp_path / "transcript.md"

    run_with_transcript(path, output, replies=["y", "s", "q"], step_by_step=True)

    assert output.read_text().endswith(
        textwrap.dedent(
            """\

            === One ===
                echo one
            skipped (--step)

            === Two ===
                echo two

            --- finished: aborted at "Two"
            """
        )
    )


def test_transcript_writes_nothing_when_the_run_is_not_started(tmp_path):
    """Declining to start runs nothing, so there's nothing to record and no file is made."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")
    output = tmp_path / "logs" / "transcript.md"

    run_with_transcript(path, output, replies=["n"])

    assert not output.exists()
    assert not output.parent.exists()


def test_transcript_creates_missing_parent_directories(tmp_path):
    """The transcript's directory is made if it doesn't exist yet."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")
    output = tmp_path / "logs" / "2026" / "transcript.md"

    run_with_transcript(path, output)

    assert output.read_text().startswith("--- paulrun PUBLISHING.md @ 2026-10-07T10:02:13+01:00\n\n")


def test_transcript_leaves_out_the_inputs_line_when_there_are_none(tmp_path):
    """A runbook without inputs has no inputs line in its header."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")
    output = tmp_path / "transcript.md"

    run_with_transcript(path, output)

    assert output.read_text().startswith("--- paulrun PUBLISHING.md @ 2026-10-07T10:02:13+01:00\n\n=== Only ===\n")


def test_transcript_is_written_as_the_run_goes(tmp_path):
    """Each line is in the file as soon as it happens, so a crash part way still leaves a record up to there."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\necho hi\n```\n")
    output = tmp_path / "transcript.md"
    seen_when_finishing: list[str] = []
    transcript = Transcript(output, path.name, clock=lambda: STARTED)

    def sink(event: runner.Event) -> None:
        if isinstance(event, runner.RunFinished):
            seen_when_finishing.append(output.read_text())
        transcript(event)

    with transcript:
        runner.run(parse(path), load_backends(), sink, FakePrompter())

    [before_finishing] = seen_when_finishing
    assert without_durations(before_finishing).endswith("=== Only ===\n    echo hi\nhi\nexit 0 (Xs)\n")


def test_transcript_path_fills_in_plain_inputs_relative_to_the_runbook(tmp_path):
    """output_path has placeholders filled in and is resolved from the runbook's directory, wherever paulrun runs."""
    path = write_runbook(tmp_path, "---\ntitle: T\noutput_path: logs/release-<VERSION>.md\n---\n")

    assert transcript_path(parse(path), {"VERSION": "1.2.0"}) == tmp_path / "logs" / "release-1.2.0.md"


def test_transcript_path_keeps_an_absolute_output_path(tmp_path):
    """An absolute output_path is used as it is."""
    target = tmp_path / "elsewhere" / "log.md"
    path = write_runbook(tmp_path, f"---\ntitle: T\noutput_path: {target}\n---\n")

    assert transcript_path(parse(path), {}) == target


def test_transcript_path_is_none_without_output_path(tmp_path):
    """No output_path means no transcript."""
    path = write_runbook(tmp_path, "---\ntitle: T\n---\n")

    assert transcript_path(parse(path), {}) is None


def test_transcript_for_a_runbook_goes_to_its_output_path_with_inputs_filled_in(tmp_path, monkeypatch):
    """Made from a runbook, a transcript works out its file from output_path once the inputs are known."""
    monkeypatch.setenv("VERSION", "1.2.0")
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        output_path: logs/release-<VERSION>.md
        inputs:
          - name: VERSION
            description: The version
        ---

        ## Only

        ```sh run
        echo "<VERSION>"
        ```
        """,
    )
    parsed = parse(path)
    transcript = Transcript.for_runbook(parsed, clock=lambda: STARTED)

    with transcript:
        runner.run(parsed, load_backends(), transcript, FakePrompter())

    assert transcript.path == tmp_path / "logs" / "release-1.2.0.md"
    assert transcript.path is not None
    assert transcript.path.read_text().startswith("--- paulrun PUBLISHING.md @ 2026-10-07T10:02:13+01:00\n")


def test_transcript_that_cannot_be_opened_raises_a_transcript_error(tmp_path):
    """A path that can't be written gives a TranscriptError naming the file, not a bare OSError."""
    (tmp_path / "logs").write_text("a file where the transcript's directory should be")
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntouch ran\n```\n")
    output = tmp_path / "logs" / "transcript.md"

    with pytest.raises(TranscriptError) as error:
        run_with_transcript(path, output)

    assert str(error.value).startswith(f"can't write the transcript to {output}: ")
    assert not (tmp_path / "ran").exists()


def test_transcript_that_fails_part_way_raises_a_transcript_error(tmp_path, monkeypatch):
    """A write that fails after the file is open, e.g. a full disk, is a TranscriptError too."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\necho hi\n```\n")
    output = tmp_path / "transcript.md"
    real_open = Path.open

    def open_then_fill_up(self, *args, **kwargs):
        file = real_open(self, *args, **kwargs)
        if self == output:
            real_write = file.write
            calls = []

            def write(text):
                calls.append(text)
                if len(calls) > 1:
                    raise OSError(28, "No space left on device")
                return real_write(text)

            file.write = write
        return file

    monkeypatch.setattr(Path, "open", open_then_fill_up)

    with pytest.raises(TranscriptError) as error:
        run_with_transcript(path, output)

    assert str(error.value) == f"can't write the transcript to {output}: No space left on device"


def test_transcript_is_written_only_once_a_step_starts(tmp_path):
    """written says whether the run got far enough to make a transcript."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")
    declined = Transcript(tmp_path / "declined.md", path.name, clock=lambda: STARTED)
    started = Transcript(tmp_path / "started.md", path.name, clock=lambda: STARTED)

    with declined:
        runner.run(parse(path), load_backends(), declined, FakePrompter(["n"]))
    with started:
        runner.run(parse(path), load_backends(), started, FakePrompter())

    assert not declined.written
    assert started.written


def test_transcript_records_an_interrupted_run(tmp_path):
    """Ctrl-C finishes the transcript as interrupted at its step, after the stopped block's exit line."""
    output = tmp_path / "transcript.md"
    transcript = Transcript(output, "PUBLISHING.md", clock=lambda: STARTED)
    step = parse(write_runbook(tmp_path, "## Slow\n\n```sh run\nsleep 60\n```\n")).steps[0]
    [block] = step.blocks

    with transcript:
        for event in [
            runner.Overview("T", (step,), 1, ()),
            runner.StepStarted(step),
            runner.BlockStarted(block, "sleep 60\n"),
            runner.OutputLine("stopping"),
            runner.BlockFinished(block, 130, 2.1),
            runner.RunFinished("interrupted", 2.2, step),
        ]:
            transcript(event)

    assert output.read_text().endswith(
        '=== Slow ===\n    sleep 60\nstopping\nexit 130 (2.1s)\n\n--- finished: interrupted at "Slow"\n'
    )


def test_transcript_records_each_input_block_where_it_was_asked(tmp_path, monkeypatch):
    """An input block's value is recorded where it was given, with a secret as ****."""
    monkeypatch.delenv("PR", raising=False)
    monkeypatch.delenv("OTP", raising=False)
    path = write_runbook(
        tmp_path,
        """\
        ## Open the pull request

        ```input
        name: PR
        description: The pull request number
        ```

        ```input
        name: OTP
        description: The one-time code
        secret: true
        ```

        ```sh run
        echo "PR <PR> with $OTP"
        ```
        """,
    )
    output = tmp_path / "transcript.md"

    class Answers(FakePrompter):
        def __init__(self):
            super().__init__()
            self.answers = ["42", "123456"]

        def ask(self, input: Input, problem: str | None) -> str:
            return self.answers.pop(0)

    transcript = Transcript(output, path.name, clock=lambda: STARTED)
    with transcript:
        runner.run(parse(path), load_backends(), transcript, Answers())

    text = without_durations(output.read_text())
    assert "=== Open the pull request ===\ninput: PR=42\ninput: OTP=****\n" in text
    assert "PR 42 with ****\n" in text
    assert "123456" not in text
