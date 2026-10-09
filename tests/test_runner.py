"""Tests for running a runbook's steps. Blocks really run under bash in tmp_path."""

import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from paulrun import runner
from paulrun.backends import load_backends
from paulrun.inputs import Input
from paulrun.runbook import parse

# A runbook with one plain input and one secret, for the input tests.
INPUTS_FRONTMATTER = """\
---
title: Inputs
inputs:
  - name: VERSION
    description: The version
  - name: TOKEN
    description: A token
    secret: true
---
"""


@dataclass
class FakePrompter:
    """Answers input prompts from answers and questions from replies, in order, recording what it was asked.

    Once replies run out, every question is answered y, so the run starts and goes past every confirm.
    """

    answers: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)

    def ask(self, input: Input, problem: str | None) -> str:
        assert self.answers, f"unexpected prompt for {input.name}"
        self.asked.append(input.name)
        return self.answers.pop(0)

    def confirm(self, question: str) -> str:
        self.questions.append(question)
        return self.replies.pop(0) if self.replies else "y"


def write_runbook(directory: Path, text: str) -> Path:
    """Write a dedented runbook.md into directory, creating it if needed, and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "runbook.md"
    path.write_text(textwrap.dedent(text))
    return path


def run(
    path: Path, prompter: FakePrompter | None = None, *, dry: bool = False
) -> tuple[list[runner.Event], runner.RunFinished]:
    """Run the runbook at path with the installed backends, returning every event sent and the result.

    Without a prompter, asking for an input fails the test and every question is answered y.
    """
    events: list[runner.Event] = []
    result = runner.run(parse(path), load_backends(), events.append, prompter or FakePrompter(), dry=dry)
    return events, result


def output(events: list[runner.Event]) -> list[str]:
    """The lines blocks printed, in order."""
    return [event.text for event in events if isinstance(event, runner.OutputLine)]


def test_run_sends_events_for_each_step_and_block_in_order(tmp_path):
    """The overview comes first, then each step starts and each of its blocks starts, prints and finishes."""
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
        runner.Overview,
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

    runner.run(parse(path), load_backends(), sink, FakePrompter())

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
        runner.run(parse(path), load_backends(), events.append, FakePrompter())

    assert str(error.value) == "line 9: no backend runs 'cobol' blocks"
    assert events == []
    assert not (tmp_path / "first-step-ran").exists()


def test_run_gives_every_input_to_blocks_as_environment_variables(tmp_path, monkeypatch):
    """Plain and secret inputs alike are exported to each block's environment."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + '\n## Env\n\n```sh run\necho "$VERSION ${#TOKEN}"\n```\n')

    events, _ = run(path, FakePrompter(answers=["1.2.0", "s3cret"]))

    assert output(events) == ["1.2.0 6"]


def test_run_substitutes_plain_inputs_into_run_blocks_before_running_them(tmp_path, monkeypatch):
    """<VERSION> is replaced in the code the backend runs, and the code event shows what ran."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + "\n## Tag\n\n```sh run\necho 'tag <VERSION>'\n```\n")

    events, _ = run(path, FakePrompter(answers=["1.2.0", "s3cret"]))

    assert [event.code for event in events if isinstance(event, runner.BlockStarted)] == ["echo 'tag 1.2.0'\n"]
    assert output(events) == ["tag 1.2.0"]


def test_run_never_substitutes_secrets(tmp_path, monkeypatch):
    """A secret's placeholder is left as written, so its value never ends up in the code."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + "\n## Leak\n\n```sh run\necho '<TOKEN>'\n```\n")

    events, _ = run(path, FakePrompter(answers=["1.2.0", "s3cret"]))

    assert [event.code for event in events if isinstance(event, runner.BlockStarted)] == ["echo '<TOKEN>'\n"]
    assert output(events) == ["<TOKEN>"]


def test_run_masks_secret_values_in_block_output(tmp_path, monkeypatch):
    """A block that prints a secret has it replaced with ****, so its value is in no event."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + '\n## Leak\n\n```sh run\necho "token is $TOKEN"\n```\n')

    events, _ = run(path, FakePrompter(answers=["1.2.0", "s3cret"]))

    assert output(events) == ["token is ****"]
    assert "s3cret" not in repr(events)


def test_run_takes_inputs_from_the_environment_without_prompting(tmp_path, monkeypatch):
    """Inputs set in paulrun's environment are used as they are."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + '\n## Env\n\n```sh run\necho "<VERSION> $TOKEN"\n```\n')

    events, _ = run(path)

    assert output(events) == ["1.2.0 ****"]


def test_run_collects_inputs_before_the_first_step_starts(tmp_path, monkeypatch):
    """Every input is asked for up front, before anything runs."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + "\n## First\n\n```sh run\ntrue\n```\n")
    events: list[runner.Event] = []
    events_when_asked: list[int] = []

    class CountingPrompter:
        def ask(self, input: Input, problem: str | None) -> str:
            events_when_asked.append(len(events))
            return "answer"

        def confirm(self, question: str) -> str:
            return "y"

    runner.run(parse(path), load_backends(), events.append, CountingPrompter())

    assert events_when_asked == [0, 0]


def test_run_does_not_ask_for_inputs_when_a_block_has_no_backend(tmp_path, monkeypatch):
    """A runbook that can't run is rejected before anyone types a secret into it."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + "\n## No backend\n\n```cobol run\nDISPLAY 'HELLO'.\n```\n")
    prompter = FakePrompter(answers=["1.2.0", "s3cret"])

    with pytest.raises(runner.RunnerError):
        run(path, prompter)

    assert prompter.asked == []


def test_run_shows_an_overview_after_collecting_inputs_then_asks_to_start(tmp_path, monkeypatch):
    """The title, steps and number of run blocks are sent once inputs are in, and then paulrun asks to start."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(
        tmp_path,
        INPUTS_FRONTMATTER
        + textwrap.dedent(
            """\

            ## First

            ```sh run
            true
            ```

            ```docstring
            Not a run block.
            ```

            ## Second

            ```sh run
            true
            ```

            ```sh run
            true
            ```
            """
        ),
    )
    events: list[runner.Event] = []
    prompted: list[tuple[str, int]] = []

    class RecordingPrompter:
        def ask(self, input: Input, problem: str | None) -> str:
            prompted.append((input.name, len(events)))
            return "answer"

        def confirm(self, question: str) -> str:
            prompted.append((question, len(events)))
            return "y"

    runner.run(parse(path), load_backends(), events.append, RecordingPrompter())

    overview = events[0]
    assert isinstance(overview, runner.Overview)
    assert overview.title == "Inputs"
    assert [step.name for step in overview.steps] == ["First", "Second"]
    assert overview.run_blocks == 3
    assert prompted == [("VERSION", 0), ("TOKEN", 0), ("Start? [y/N]", 1)]


def test_run_overview_uses_the_file_name_when_there_is_no_title(tmp_path):
    """A runbook with no title is shown by its file name."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")

    events, _ = run(path)

    assert events[0] == runner.Overview(title="runbook.md", steps=parse(path).steps, run_blocks=1, inputs=())


@pytest.mark.parametrize("reply", ["", "n", "no", "yes", "Y"])
def test_run_runs_nothing_unless_the_answer_to_start_is_y(tmp_path, reply):
    """Only y starts the run. Any other answer aborts it before the first step."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntouch ran\n```\n")

    events, result = run(path, FakePrompter(replies=[reply]))

    assert not (tmp_path / "ran").exists()
    assert [type(event) for event in events] == [runner.Overview, runner.RunFinished]
    assert result.status == "aborted"
    assert result.step is None


def test_run_ignores_spaces_around_a_y(tmp_path):
    """A y with stray spaces around it still counts as y."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntouch ran\n```\n")

    _, result = run(path, FakePrompter(replies=[" y "]))

    assert (tmp_path / "ran").exists()
    assert result.status == "ok"


def test_run_sends_docstring_and_confirm_blocks_in_order_with_run_blocks(tmp_path):
    """Every block in a step is sent in the order it's written, whatever its kind."""
    path = write_runbook(
        tmp_path,
        """\
        ## Mixed

        ```docstring
        About to check.
        ```

        ```confirm
        Check it by hand.
        ```

        ```sh run
        echo checked
        ```
        """,
    )

    events, _ = run(path)

    assert [type(event) for event in events] == [
        runner.Overview,
        runner.StepStarted,
        runner.Docstring,
        runner.Confirm,
        runner.BlockStarted,
        runner.OutputLine,
        runner.BlockFinished,
        runner.RunFinished,
    ]


def test_run_substitutes_plain_inputs_into_docstring_and_confirm_text(tmp_path, monkeypatch):
    """<VERSION> is replaced in docstring and confirm text, and a secret's placeholder is left as written."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(
        tmp_path,
        INPUTS_FRONTMATTER
        + textwrap.dedent(
            """\

            ## Release

            ```docstring
            Releasing <VERSION> with <TOKEN>.
            ```

            ```confirm
            Tag <VERSION> on GitHub.
            ```
            """
        ),
    )

    events, _ = run(path, FakePrompter(answers=["1.2.0", "s3cret"]))

    [docstring] = [event for event in events if isinstance(event, runner.Docstring)]
    [confirm] = [event for event in events if isinstance(event, runner.Confirm)]
    assert docstring.text == "Releasing 1.2.0 with <TOKEN>.\n"
    assert confirm.text == "Tag 1.2.0 on GitHub.\n"


def test_run_asks_to_continue_after_each_confirm_and_carries_on_after_y(tmp_path):
    """A confirm block waits for an answer, and y carries on with the rest of the run."""
    path = write_runbook(
        tmp_path,
        """\
        ## Manual

        ```confirm
        Do the manual thing.
        ```

        ```sh run
        touch ran
        ```
        """,
    )
    prompter = FakePrompter(replies=["y", "y"])

    _, result = run(path, prompter)

    assert prompter.questions == ["Start? [y/N]", "Continue? [y/N]"]
    assert (tmp_path / "ran").exists()
    assert result.status == "ok"


@pytest.mark.parametrize("reply", ["", "n", "yes"])
def test_run_aborts_at_a_confirm_not_answered_y(tmp_path, reply):
    """Any answer but y to a confirm stops the run there: nothing after it runs, in its step or later ones."""
    path = write_runbook(
        tmp_path,
        """\
        ## Before

        ```sh run
        touch before-ran
        ```

        ## Manual

        ```confirm
        Do the manual thing.
        ```

        ```sh run
        touch same-step-ran
        ```

        ## After

        ```sh run
        touch later-step-ran
        ```
        """,
    )

    events, result = run(path, FakePrompter(replies=["y", reply]))

    assert (tmp_path / "before-ran").exists()
    assert not (tmp_path / "same-step-ran").exists()
    assert not (tmp_path / "later-step-ran").exists()
    assert [event.step.name for event in events if isinstance(event, runner.StepStarted)] == ["Before", "Manual"]
    assert result.status == "aborted"
    assert result.step is not None
    assert result.step.name == "Manual"
    assert result.exit_code is None


def test_run_overview_lists_inputs_with_secrets_masked(tmp_path, monkeypatch):
    """The overview shows each input's value in declared order, with **** in place of each secret."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + "\n## Only\n\n```sh run\ntrue\n```\n")

    events, _ = run(path)

    overview = events[0]
    assert isinstance(overview, runner.Overview)
    assert overview.inputs == (("VERSION", "1.2.0"), ("TOKEN", "****"))


def test_dry_run_runs_nothing(tmp_path):
    """No block runs under dry, so nothing it would have done happens."""
    path = write_runbook(
        tmp_path,
        """\
        ## First

        ```sh run
        touch first-ran
        ```

        ## Second

        ```sh run
        touch second-ran
        ```
        """,
    )

    events, result = run(path, dry=True)

    assert not (tmp_path / "first-ran").exists()
    assert not (tmp_path / "second-ran").exists()
    assert output(events) == []
    assert result.status == "dry"


def test_dry_run_sends_every_step_and_block_in_order_without_finishing_any(tmp_path):
    """A dry run goes through the whole runbook like a real one, but no run block finishes because none ran."""
    path = write_runbook(
        tmp_path,
        """\
        ## First

        ```docstring
        About to build.
        ```

        ```sh run
        echo one
        ```

        ## Second

        ```confirm
        Check it by hand.
        ```

        ```sh run
        exit 3
        ```
        """,
    )

    events, _ = run(path, dry=True)

    assert [type(event) for event in events] == [
        runner.Overview,
        runner.StepStarted,
        runner.Docstring,
        runner.BlockStarted,
        runner.StepStarted,
        runner.Confirm,
        runner.BlockStarted,
        runner.RunFinished,
    ]


def test_dry_run_asks_no_questions(tmp_path):
    """There's no start prompt and confirms don't wait, so a dry run can't be aborted part way."""
    path = write_runbook(
        tmp_path,
        """\
        ## Manual

        ```confirm
        Do the manual thing.
        ```

        ```sh run
        true
        ```
        """,
    )
    prompter = FakePrompter(replies=["n", "n"])

    _, result = run(path, prompter, dry=True)

    assert prompter.questions == []
    assert result.status == "dry"


def test_dry_run_substitutes_plain_inputs_into_every_block(tmp_path, monkeypatch):
    """Run, docstring and confirm blocks show plain inputs filled in, exactly as a real run would."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(
        tmp_path,
        INPUTS_FRONTMATTER
        + textwrap.dedent(
            """\

            ## Release

            ```docstring
            Releasing <VERSION>.
            ```

            ```confirm
            Tag <VERSION>.
            ```

            ```sh run
            git tag <VERSION> && echo "$TOKEN"
            ```
            """
        ),
    )

    events, _ = run(path, dry=True)

    assert [event.text for event in events if isinstance(event, runner.Docstring)] == ["Releasing 1.2.0.\n"]
    assert [event.text for event in events if isinstance(event, runner.Confirm)] == ["Tag 1.2.0.\n"]
    assert [event.code for event in events if isinstance(event, runner.BlockStarted)] == [
        'git tag 1.2.0 && echo "$TOKEN"\n'
    ]


def test_dry_run_collects_plain_inputs_but_never_asks_for_secrets(tmp_path, monkeypatch):
    """Plain inputs are still asked for, so the blocks can be shown filled in, but secrets aren't needed."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + "\n## Only\n\n```sh run\ntrue\n```\n")
    prompter = FakePrompter(answers=["1.2.0"])

    events, _ = run(path, prompter, dry=True)

    assert prompter.asked == ["VERSION"]
    overview = events[0]
    assert isinstance(overview, runner.Overview)
    assert overview.inputs == (("VERSION", "1.2.0"), ("TOKEN", "****"))


def test_dry_run_ignores_a_secret_set_in_the_environment(tmp_path, monkeypatch):
    """A secret from the environment is never read under dry, so a bad value can't stop it and it's shown as ****."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + "\n## Only\n\n```sh run\ntrue\n```\n")

    events, _ = run(path, dry=True)

    assert "s3cret" not in repr(events)


def test_dry_run_still_rejects_a_block_with_no_backend(tmp_path):
    """A dry run checks what a real run would, so it catches a block nothing can run."""
    path = write_runbook(tmp_path, "## No backend\n\n```cobol run\nDISPLAY 'HELLO'.\n```\n")

    with pytest.raises(runner.RunnerError):
        run(path, dry=True)
