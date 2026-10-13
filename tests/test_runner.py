"""Tests for running a runbook's steps. Blocks really run under bash in tmp_path."""

import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from paulrun import runner
from paulrun.backends import Interrupted, load_backends
from paulrun.inputs import Input, InputError
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
    path: Path,
    prompter: FakePrompter | None = None,
    *,
    cwd: Path | None = None,
    dry: bool = False,
    step_by_step: bool = False,
) -> tuple[list[runner.Event], runner.RunFinished]:
    """Run the runbook at path with the installed backends, returning every event sent and the result.

    Without a prompter, asking for an input fails the test and every question is answered y. Blocks run in
    cwd, or the runbook's directory if it isn't given.
    """
    events: list[runner.Event] = []
    result = runner.run(
        parse(path),
        load_backends(),
        events.append,
        prompter or FakePrompter(),
        cwd=cwd or path.parent,
        dry=dry,
        step_by_step=step_by_step,
    )
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

    runner.run(parse(path), load_backends(), sink, FakePrompter(), cwd=path.parent)

    assert len(arrivals) == 3
    assert arrivals[2] - arrivals[0] >= 0.3


def test_run_runs_blocks_in_the_directory_it_is_given(tmp_path):
    """Blocks run in the cwd they're given, not where the runbook is."""
    path = write_runbook(tmp_path / "book", "## Where\n\n```sh run\npwd -P\n```\n")
    (tmp_path / "project").mkdir()

    events, _ = run(path, cwd=tmp_path / "project")

    assert output(events) == [str((tmp_path / "project").resolve())]


def test_run_runs_python_blocks_in_the_directory_it_is_given(tmp_path):
    """Python blocks run in the given cwd too, though each is written to a temporary file somewhere else."""
    path = write_runbook(tmp_path / "book", "## Where\n\n```python run\nimport os\nprint(os.getcwd())\n```\n")
    (tmp_path / "project").mkdir()

    events, _ = run(path, cwd=tmp_path / "project")

    assert output(events) == [str((tmp_path / "project").resolve())]


def test_run_tells_blocks_where_the_runbook_is(tmp_path, monkeypatch):
    """PAULRUN_RUNBOOK_DIR is the runbook's directory as an absolute path, even if paulrun was given a relative one."""
    write_runbook(tmp_path / "book", '## Where\n\n```sh run\necho "$PAULRUN_RUNBOOK_DIR"\n```\n')
    (tmp_path / "project").mkdir()
    monkeypatch.chdir(tmp_path / "project")

    events, _ = run(Path("../book/runbook.md"), cwd=tmp_path / "project")

    assert output(events) == [str((tmp_path / "book").resolve())]


def test_run_sets_paulrun_runbook_dir_over_one_already_in_the_environment(tmp_path, monkeypatch):
    """A PAULRUN_RUNBOOK_DIR left over from an outer run is replaced, so a block never sees the wrong runbook's."""
    monkeypatch.setenv("PAULRUN_RUNBOOK_DIR", "/somewhere/else")
    path = write_runbook(tmp_path / "book", '## Where\n\n```sh run\necho "$PAULRUN_RUNBOOK_DIR"\n```\n')

    events, _ = run(path, cwd=tmp_path)

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
        runner.run(parse(path), load_backends(), events.append, FakePrompter(), cwd=path.parent)

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

    runner.run(parse(path), load_backends(), events.append, CountingPrompter(), cwd=path.parent)

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

    runner.run(parse(path), load_backends(), events.append, RecordingPrompter(), cwd=path.parent)

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
        runner.ConfirmAnswered,
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


# Three steps of one run block each, for the step_by_step tests. Each block leaves a file behind if it runs.
THREE_STEPS = """\
## Build

```sh run
touch built
```

## Publish

```sh run
touch published
```

## Announce

```sh run
touch announced
```
"""


def test_step_by_step_runs_each_block_answered_y(tmp_path):
    """After each run block's code, paulrun asks about it, and y runs it."""
    path = write_runbook(tmp_path, THREE_STEPS)
    prompter = FakePrompter(replies=["y", "y", "y", "y"])

    _, result = run(path, prompter, step_by_step=True)

    assert prompter.questions == ["Start? [y/N]"] + ["Run this block? [y]es / [s]kip / [q]uit"] * 3
    assert (tmp_path / "built").exists()
    assert (tmp_path / "published").exists()
    assert (tmp_path / "announced").exists()
    assert result.status == "ok"


def test_step_by_step_skips_a_block_answered_s_and_carries_on(tmp_path):
    """s skips the block, which is sent as skipped instead of finished, and the run goes on to the next one."""
    path = write_runbook(tmp_path, THREE_STEPS)

    events, result = run(path, FakePrompter(replies=["y", "y", "s", "y"]), step_by_step=True)

    assert (tmp_path / "built").exists()
    assert not (tmp_path / "published").exists()
    assert (tmp_path / "announced").exists()
    assert [type(event) for event in events] == [
        runner.Overview,
        runner.StepStarted,
        runner.BlockStarted,
        runner.BlockFinished,
        runner.StepStarted,
        runner.BlockStarted,
        runner.BlockSkipped,
        runner.StepStarted,
        runner.BlockStarted,
        runner.BlockFinished,
        runner.RunFinished,
    ]
    [skipped] = [event for event in events if isinstance(event, runner.BlockSkipped)]
    assert skipped.block.content == "touch published\n"
    assert result.status == "ok"


def test_step_by_step_quits_at_a_block_answered_q(tmp_path):
    """q stops the run before the block: it and everything after it are left, and the run is aborted at its step."""
    path = write_runbook(tmp_path, THREE_STEPS)

    events, result = run(path, FakePrompter(replies=["y", "y", "q"]), step_by_step=True)

    assert (tmp_path / "built").exists()
    assert not (tmp_path / "published").exists()
    assert not (tmp_path / "announced").exists()
    assert not [event for event in events if isinstance(event, runner.BlockSkipped)]
    assert result.status == "aborted"
    assert result.step is not None
    assert result.step.name == "Publish"
    assert result.exit_code is None


@pytest.mark.parametrize("reply", ["", "n", "Y", "yes", "skip"])
def test_step_by_step_asks_again_until_the_answer_is_y_s_or_q(tmp_path, reply):
    """Any other answer gets the question again, and nothing runs until it's answered."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntouch ran\n```\n")
    prompter = FakePrompter(replies=["y", reply, reply, "y"])

    run(path, prompter, step_by_step=True)

    assert prompter.questions == ["Start? [y/N]"] + ["Run this block? [y]es / [s]kip / [q]uit"] * 3
    assert (tmp_path / "ran").exists()


def test_step_by_step_ignores_spaces_around_the_answer(tmp_path):
    """An s with stray spaces around it still skips."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntouch ran\n```\n")

    _, result = run(path, FakePrompter(replies=["y", " s "]), step_by_step=True)

    assert not (tmp_path / "ran").exists()
    assert result.status == "ok"


def test_step_by_step_asks_once_the_block_code_has_been_sent(tmp_path):
    """The question comes after the code, so it's about code that's already on screen."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")
    events: list[runner.Event] = []
    last_event_when_asked: dict[str, type] = {}

    class RecordingPrompter:
        def ask(self, input: Input, problem: str | None) -> str:
            raise AssertionError(f"unexpected prompt for {input.name}")

        def confirm(self, question: str) -> str:
            last_event_when_asked[question] = type(events[-1])
            return "y"

    runner.run(parse(path), load_backends(), events.append, RecordingPrompter(), step_by_step=True, cwd=path.parent)

    assert last_event_when_asked["Run this block? [y]es / [s]kip / [q]uit"] is runner.BlockStarted


def test_step_by_step_only_asks_about_run_blocks(tmp_path):
    """docstring blocks are just printed, and confirm blocks still ask their own question."""
    path = write_runbook(
        tmp_path,
        """\
        ## Mixed

        ```docstring
        A note.
        ```

        ```confirm
        Do the manual thing.
        ```

        ```sh run
        true
        ```
        """,
    )
    prompter = FakePrompter()

    run(path, prompter, step_by_step=True)

    assert prompter.questions == ["Start? [y/N]", "Continue? [y/N]", "Run this block? [y]es / [s]kip / [q]uit"]


def test_step_by_step_leaves_time_spent_answering_out_of_the_block_duration(tmp_path):
    """A block's duration is how long it ran, not how long someone took to answer; the run's includes both."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")

    class SlowToAnswer(FakePrompter):
        def confirm(self, question: str) -> str:
            if question.startswith("Run this block?"):
                time.sleep(0.5)
            return super().confirm(question)

    events, result = run(path, SlowToAnswer(), step_by_step=True)

    [finished] = [event for event in events if isinstance(event, runner.BlockFinished)]
    assert finished.duration < 0.4
    assert result.duration >= 0.5


def test_dry_run_ignores_step_by_step(tmp_path):
    """Nothing runs under dry, so there's nothing to ask about, and the run is exactly a plain dry run."""
    path = write_runbook(tmp_path, THREE_STEPS)
    prompter = FakePrompter(replies=["q", "q", "q", "q"])

    stepped, stepped_result = run(path, prompter, dry=True, step_by_step=True)
    plain, _ = run(path, dry=True)

    assert prompter.questions == []
    assert stepped[:-1] == plain[:-1]
    assert stepped_result.status == "dry"


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0.04, "0.0s"),
        (4.23, "4.2s"),
        (59.94, "59.9s"),
        (59.96, "1m00s"),
        (192, "3m12s"),
        (3605, "60m05s"),
    ],
)
def test_duration_is_tenths_of_seconds_under_a_minute_then_minutes_and_seconds(seconds, expected):
    """Short durations show tenths of a second; from a minute up they show minutes and whole seconds."""
    assert runner.format_duration(seconds) == expected


def test_run_sends_each_confirm_answer(tmp_path):
    """After a confirm is answered, the answer is sent, so a transcript can record it: yes for y, no otherwise."""
    path = write_runbook(
        tmp_path,
        """\
        ## Manual

        ```confirm
        First check.
        ```

        ```confirm
        Second check.
        ```
        """,
    )

    events, _ = run(path, FakePrompter(replies=["y", "y", "nope"]))

    answers = [event for event in events if isinstance(event, runner.ConfirmAnswered)]
    assert [(answer.text, answer.yes) for answer in answers] == [("First check.\n", True), ("Second check.\n", False)]
    assert isinstance(events[-2], runner.ConfirmAnswered)
    assert isinstance(events[-1], runner.RunFinished)


def test_dry_run_sends_no_confirm_answers(tmp_path):
    """Under dry nothing is asked, so there are no answers to send."""
    path = write_runbook(tmp_path, "## Manual\n\n```confirm\nCheck it.\n```\n")

    events, _ = run(path, dry=True)

    assert not [event for event in events if isinstance(event, runner.ConfirmAnswered)]


def test_run_masks_a_secret_value_written_into_the_runbook_itself(tmp_path, monkeypatch):
    """If a secret's value also appears in the runbook's own text, it's masked in every text paulrun sends."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release s3cret
        inputs:
          - name: VERSION
            description: The version
          - name: TOKEN
            description: A token
            secret: true
        ---

        ## Step s3cret

        ```docstring
        Docstring s3cret.
        ```

        ```confirm
        Confirm s3cret.
        ```

        ```sh run
        echo "code s3cret $TOKEN <VERSION>"
        ```
        """,
    )

    events, _ = run(path, FakePrompter(replies=["y", "n"]))

    overview, step_started, docstring, confirm, _, finished = events
    assert isinstance(overview, runner.Overview)
    assert overview.title == "Release ****"
    assert [step.name for step in overview.steps] == ["Step ****"]
    assert isinstance(step_started, runner.StepStarted)
    assert step_started.step.name == "Step ****"
    assert isinstance(docstring, runner.Docstring)
    assert docstring.text == "Docstring ****.\n"
    assert isinstance(confirm, runner.Confirm)
    assert confirm.text == "Confirm ****.\n"
    assert isinstance(finished, runner.RunFinished)
    assert finished.step is not None
    assert finished.step.name == "Step ****"


def test_run_masks_a_secret_value_in_code_it_shows_but_runs_the_real_code(tmp_path, monkeypatch):
    """The code shown has a secret's value masked, but the backend still runs the code as written."""
    monkeypatch.setenv("TOKEN", "s3cret")
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        inputs:
          - name: TOKEN
            description: A token
            secret: true
        ---

        ## Step

        ```sh run
        test "$TOKEN" = s3cret && echo "matched"
        ```
        """,
    )

    events, _ = run(path)

    [started] = [event for event in events if isinstance(event, runner.BlockStarted)]
    assert started.code == 'test "$TOKEN" = **** && echo "matched"\n'
    assert output(events) == ["matched"]


def test_code_lines_indents_each_line_and_leaves_blank_lines_empty():
    """Code is shown four spaces in, and a blank line inside a block stays blank, without trailing spaces."""
    assert runner.code_lines("first\n\n  nested\nlast\n") == ["    first", "", "      nested", "    last"]


class InterruptedBackend:
    """A backend whose block is stopped by Ctrl-C, as stream() reports it: output first, then Interrupted."""

    name = "interrupted"
    languages = ("stopped",)

    def validate(self, code):
        return []

    def run(self, code, *, frontmatter, env, cwd, output):
        output("cleaning up")
        raise Interrupted(130)


def test_run_finishes_as_interrupted_when_a_block_is_stopped_by_ctrl_c(tmp_path):
    """The stopped block's output and exit code are sent, nothing after it runs, and the run ends as interrupted."""
    path = write_runbook(
        tmp_path,
        """\
        ## Before

        ```sh run
        true
        ```

        ## Slow

        ```stopped run
        anything
        ```

        ## After

        ```sh run
        touch ran
        ```
        """,
    )
    events: list[runner.Event] = []

    result = runner.run(
        parse(path),
        {**load_backends(), "stopped": InterruptedBackend()},
        events.append,
        FakePrompter(),
        cwd=path.parent,
    )

    assert result.status == "interrupted"
    assert result.step is not None
    assert result.step.name == "Slow"
    assert output(events)[-1] == "cleaning up"
    finished = [event for event in events if isinstance(event, runner.BlockFinished)]
    assert [event.exit_code for event in finished] == [0, 130]
    assert events[-1] is result
    assert not (tmp_path / "ran").exists()


def test_run_finishes_as_interrupted_on_ctrl_c_at_a_confirm(tmp_path):
    """Ctrl-C while waiting at a confirm ends the run at that step, with no answer sent."""
    path = write_runbook(tmp_path, "## Manual\n\n```confirm\nDo it.\n```\n\n```sh run\ntouch ran\n```\n")

    class CtrlCAtConfirm(FakePrompter):
        def confirm(self, question: str) -> str:
            if question.startswith("Continue?"):
                raise KeyboardInterrupt
            return super().confirm(question)

    events, result = run(path, CtrlCAtConfirm())

    assert result.status == "interrupted"
    assert result.step is not None
    assert result.step.name == "Manual"
    assert not [event for event in events if isinstance(event, runner.ConfirmAnswered)]
    assert not (tmp_path / "ran").exists()


def test_run_finishes_as_interrupted_before_starting_on_ctrl_c_at_the_start_prompt(tmp_path):
    """Ctrl-C at the start prompt ends the run with no step, before anything runs."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntouch ran\n```\n")

    class CtrlCAtStart(FakePrompter):
        def confirm(self, question: str) -> str:
            raise KeyboardInterrupt

    events, result = run(path, CtrlCAtStart())

    assert result.status == "interrupted"
    assert result.step is None
    assert [type(event) for event in events] == [runner.Overview, runner.RunFinished]
    assert not (tmp_path / "ran").exists()


def test_run_lets_ctrl_c_while_collecting_inputs_end_the_run_unhandled(tmp_path, monkeypatch):
    """Ctrl-C while typing inputs happens before the overview, so there's no run to finish; it's left to the CLI."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)
    path = write_runbook(tmp_path, INPUTS_FRONTMATTER + "\n## Only\n\n```sh run\ntrue\n```\n")

    class CtrlCAtInput(FakePrompter):
        def ask(self, input: Input, problem: str | None) -> str:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(path, CtrlCAtInput())


# A runbook that asks for a pull request number part way through, after a manual step.
PR_RUNBOOK = """\
## Build

```sh run
echo "build"
```

## Open the pull request

```confirm
Open a pull request on GitHub.
```

```input
name: PR
description: The pull request number
pattern: '\\d+'
```

```sh run
echo "PR <PR> is $PR"
```

## Announce

```docstring
Merged PR <PR>.
```
"""


def test_run_asks_for_an_input_block_when_it_reaches_it(tmp_path, monkeypatch):
    """An input block is asked for at its place in the run, after the blocks before it, not before the first step."""
    monkeypatch.delenv("PR", raising=False)
    path = write_runbook(tmp_path, PR_RUNBOOK)
    events: list[runner.Event] = []
    seen_when_asked: list[list[type]] = []

    class RecordingPrompter(FakePrompter):
        def ask(self, input: Input, problem: str | None) -> str:
            seen_when_asked.append([type(event) for event in events])
            return "42"

    runner.run(parse(path), load_backends(), events.append, RecordingPrompter(), cwd=path.parent)

    [seen] = seen_when_asked
    # Asked once the manual step before it has been answered, and the input block itself has been shown.
    assert seen[-2:] == [runner.ConfirmAnswered, runner.InputBlock]
    assert seen.count(runner.BlockFinished) == 1  # the first step's block ran first
    assert output(events) == ["build", "PR 42 is 42"]


def test_run_gives_an_input_blocks_value_to_every_later_block(tmp_path, monkeypatch):
    """Once asked, the value is substituted and in the environment for the rest of the run, in later steps too."""
    monkeypatch.delenv("PR", raising=False)
    path = write_runbook(tmp_path, PR_RUNBOOK)

    events, result = run(path, FakePrompter(answers=["42"]))

    assert result.status == "ok"
    assert [event.code for event in events if isinstance(event, runner.BlockStarted)][-1] == 'echo "PR 42 is $PR"\n'
    assert [event.text for event in events if isinstance(event, runner.Docstring)] == ["Merged PR 42.\n"]


def test_run_sends_each_collected_input(tmp_path, monkeypatch):
    """An InputCollected event records the name and value at the block, so a transcript can show it."""
    monkeypatch.delenv("PR", raising=False)
    path = write_runbook(tmp_path, PR_RUNBOOK)

    events, _ = run(path, FakePrompter(answers=["42"]))

    [collected] = [event for event in events if isinstance(event, runner.InputCollected)]
    assert (collected.name, collected.value) == ("PR", "42")
    assert collected.block.line == 13


def test_run_takes_an_input_blocks_value_from_the_environment(tmp_path, monkeypatch):
    """An input block set in the environment isn't asked for, like any input."""
    monkeypatch.setenv("PR", "7")
    path = write_runbook(tmp_path, PR_RUNBOOK)

    events, _ = run(path)

    assert output(events)[-1] == "PR 7 is 7"


def test_run_asks_again_when_an_input_blocks_answer_does_not_match(tmp_path, monkeypatch):
    """A typed answer that doesn't match the block's pattern is refused and asked for again."""
    monkeypatch.delenv("PR", raising=False)
    path = write_runbook(tmp_path, PR_RUNBOOK)
    prompter = FakePrompter(answers=["latest", "42"])

    events, _ = run(path, prompter)

    assert prompter.asked == ["PR", "PR"]
    assert output(events)[-1] == "PR 42 is 42"


def test_run_masks_a_secret_input_block_from_then_on(tmp_path, monkeypatch):
    """A secret typed at an input block is in the environment, but shown as **** in everything sent after it."""
    monkeypatch.delenv("OTP", raising=False)
    path = write_runbook(
        tmp_path,
        """\
        ## Publish

        ```input
        name: OTP
        description: The one-time code
        secret: true
        ```

        ```sh run
        echo "code is $OTP"
        ```
        """,
    )

    events, _ = run(path, FakePrompter(answers=["123456"]))

    assert output(events) == ["code is ****"]
    [collected] = [event for event in events if isinstance(event, runner.InputCollected)]
    assert collected.value == "****"
    assert "123456" not in repr(events)


def test_dry_run_does_not_ask_for_input_blocks(tmp_path, monkeypatch):
    """Under dry the value may not exist yet, so it isn't asked for, and later blocks show <NAME> as written."""
    monkeypatch.delenv("PR", raising=False)
    path = write_runbook(tmp_path, PR_RUNBOOK)
    prompter = FakePrompter()

    events, result = run(path, prompter, dry=True)

    assert prompter.asked == []
    assert not [event for event in events if isinstance(event, runner.InputCollected)]
    assert [event.code for event in events if isinstance(event, runner.BlockStarted)][-1] == 'echo "PR <PR> is $PR"\n'
    assert result.status == "dry"


def test_dry_run_sends_input_blocks_so_they_can_be_shown(tmp_path):
    """A dry run still shows that the run would stop to ask, by sending the input block as it reaches it."""
    path = write_runbook(tmp_path, PR_RUNBOOK)

    events, _ = run(path, dry=True)

    [shown] = [event for event in events if isinstance(event, runner.InputBlock)]
    assert shown.input == Input(name="PR", description="The pull request number", pattern=r"\d+")


def test_step_by_step_does_not_ask_about_input_blocks(tmp_path, monkeypatch):
    """--step only asks about run blocks; an input block is always asked for."""
    monkeypatch.delenv("PR", raising=False)
    path = write_runbook(tmp_path, PR_RUNBOOK)
    prompter = FakePrompter(answers=["42"])

    run(path, prompter, step_by_step=True)

    assert prompter.asked == ["PR"]
    assert prompter.questions.count(runner.STEP_QUESTION) == 2


def test_run_finishes_as_interrupted_on_ctrl_c_at_an_input_block(tmp_path, monkeypatch):
    """Ctrl-C while typing at an input block ends the run at that step, with nothing collected."""
    monkeypatch.delenv("PR", raising=False)
    path = write_runbook(tmp_path, PR_RUNBOOK)

    class CtrlCAtInput(FakePrompter):
        def ask(self, input: Input, problem: str | None) -> str:
            raise KeyboardInterrupt

    events, result = run(path, CtrlCAtInput())

    assert result.status == "interrupted"
    assert result.step is not None
    assert result.step.name == "Open the pull request"
    assert not [event for event in events if isinstance(event, runner.InputCollected)]


def test_run_reports_an_input_blocks_bad_environment_value(tmp_path, monkeypatch):
    """A value from the environment that doesn't match the block's pattern stops the run there."""
    monkeypatch.setenv("PR", "latest")
    path = write_runbook(tmp_path, PR_RUNBOOK)

    with pytest.raises(InputError, match=r"PR from the environment must match \\d\+"):
        run(path)


def test_run_rejects_an_input_block_that_is_not_a_valid_input_before_running_anything(tmp_path):
    """Like a block with no backend, a malformed input block is an error up front, so nothing half-runs."""
    path = write_runbook(tmp_path, "## First\n\n```sh run\ntouch ran\n```\n\n## Ask\n\n```input\nname: PR\n```\n")
    events: list[runner.Event] = []

    with pytest.raises(runner.RunnerError) as error:
        runner.run(parse(path), load_backends(), events.append, FakePrompter(), cwd=path.parent)

    assert str(error.value) == "line 9: input block isn't a valid input; run paulrun check to see why"
    assert events == []
    assert not (tmp_path / "ran").exists()
