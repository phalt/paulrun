"""Tests for CLI commands."""

import importlib.metadata
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from paulrun import cli
from paulrun.backends import BackendError

RUNBOOKS = Path(__file__).parent / "runbooks"


@pytest.fixture
def runner(monkeypatch):
    """Fixture providing a Click CLI test runner, with plain output even if the environment forces colour."""
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    return CliRunner()


def write_runbook(tmp_path: Path, text: str) -> Path:
    """Write a dedented runbook into tmp_path and return its path."""
    path = tmp_path / "runbook.md"
    path.write_text(textwrap.dedent(text))
    return path


@pytest.fixture
def inputs_runbook(monkeypatch):
    """The inputs example runbook, with neither of its inputs set in the environment."""
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("PUBLISH_TOKEN", raising=False)
    return RUNBOOKS / "inputs-example.md"


def test_version_prints_package_version(runner):
    """--version prints the version from the installed package metadata."""
    result = runner.invoke(cli.cli, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"paulrun, version {importlib.metadata.version('paulrun')}\n"


def test_help_lists_go_command(runner):
    """--help lists the go command."""
    result = runner.invoke(cli.cli, ["--help"])

    assert result.exit_code == 0
    assert "Usage: paulrun" in result.output
    assert "\n  go " in result.output


def test_go_prints_each_step_block_and_result(runner, tmp_path):
    """go prints each step's name, each block's code, its output and exit code, then how the run finished."""
    path = write_runbook(
        tmp_path,
        """\
        ## Greet

        ```sh run
        echo hello
        echo world
        ```

        ## Again

        ```sh run
        echo again
        ```
        """,
    )

    result = runner.invoke(cli.cli, ["go", str(path)])

    assert result.exit_code == 0
    assert re.sub(r"\(\d+\.\ds\)", "(Xs)", result.output) == textwrap.dedent(
        """\

        === Greet ===
        $ echo hello
          echo world
        hello
        world
        exit 0 (Xs)

        === Again ===
        $ echo again
        again
        exit 0 (Xs)

        finished: ok (Xs)
        """
    )


def test_go_runs_blocks_in_the_runbook_directory(runner, tmp_path, monkeypatch):
    """Blocks run in the runbook's directory, not the one paulrun is started from."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli.cli, ["go", str(RUNBOOKS / "two_steps.md")])

    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert ["1", "2", "3"] == [line for line in lines if line in {"1", "2", "3"}]
    assert str(RUNBOOKS.resolve()) in lines


def test_go_stops_at_the_failing_block_and_names_its_step(runner, tmp_path):
    """A failing block ends the run with exit code 1, naming the step, and later steps don't run."""
    path = write_runbook(
        tmp_path,
        """\
        ## Passes

        ```sh run
        echo passing
        ```

        ## Fails

        ```sh run
        exit 3
        ```

        ## Never reached

        ```sh run
        echo unreachable
        ```
        """,
    )

    result = runner.invoke(cli.cli, ["go", str(path)])

    assert result.exit_code == 1
    assert "passing" in result.output.splitlines()
    assert re.search(r"^exit 3 \(\d+\.\ds\)$", result.output, re.MULTILINE)
    assert result.output.endswith('\nfinished: failed at "Fails" (exit 3)\n')
    assert "Never reached" not in result.output
    assert "unreachable" not in result.output


def test_go_prints_output_and_code_verbatim(runner, tmp_path):
    """Output and code that look like rich markup or emoji codes, and long lines, are printed exactly as they are."""
    path = write_runbook(
        tmp_path,
        """\
        ## Verbatim

        ```sh run
        echo '[bold]markup[/bold] :smile:'
        printf '%0200d\\n' 0
        ```
        """,
    )

    result = runner.invoke(cli.cli, ["go", str(path)])

    lines = result.output.splitlines()
    assert "$ echo '[bold]markup[/bold] :smile:'" in lines
    assert "[bold]markup[/bold] :smile:" in lines
    assert "0" * 200 in lines


def test_go_streams_output_line_by_line_through_a_pipe():
    """Each line is written as soon as the block prints it, even when paulrun's stdout is a pipe."""
    command = [sys.executable, "-c", "from paulrun.cli import cli; cli()", "go", str(RUNBOOKS / "two_steps.md")]
    arrivals: dict[str, float] = {}

    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True) as process:
        assert process.stdout is not None  # set because stdout is a pipe
        for line in process.stdout:
            arrivals.setdefault(line.removesuffix("\n"), time.monotonic())

    assert process.returncode == 0
    assert arrivals["3"] - arrivals["1"] >= 0.3


def test_go_rejects_missing_runbook_as_usage_error(runner, tmp_path):
    """A runbook path that doesn't exist is a usage error."""
    result = runner.invoke(cli.cli, ["go", str(tmp_path / "missing.md")])

    assert result.exit_code == 2


def test_go_reports_runbook_it_cannot_read(runner, tmp_path):
    """A runbook that can't be parsed is reported as an error, without a traceback."""
    path = write_runbook(tmp_path, "---\ntitle: Unclosed\n\n## Step\n")

    result = runner.invoke(cli.cli, ["go", str(path)])

    assert result.exit_code == 1
    assert result.output == "Error: frontmatter has no closing ---\n"


def test_go_reports_run_block_with_no_backend(runner, tmp_path):
    """A run block for a language no backend runs is reported before anything runs."""
    path = write_runbook(tmp_path, "## Step\n\n```cobol run\nDISPLAY 'HELLO'.\n```\n")

    result = runner.invoke(cli.cli, ["go", str(path)])

    assert result.exit_code == 1
    assert result.output == "Error: line 3: no backend runs 'cobol' blocks\n"


def test_go_reports_backends_that_cannot_load(runner, tmp_path, monkeypatch):
    """If the installed backends conflict, go says so instead of crashing."""

    def conflicting_backends():
        raise BackendError("language 'sh' is claimed by both 'shell' and 'rival'")

    monkeypatch.setattr(cli, "load_backends", conflicting_backends)
    path = write_runbook(tmp_path, "## Step\n\n```sh run\necho hi\n```\n")

    result = runner.invoke(cli.cli, ["go", str(path)])

    assert result.exit_code == 1
    assert result.output == "Error: language 'sh' is claimed by both 'shell' and 'rival'\n"


def test_go_prompts_for_inputs_and_uses_the_answers(runner, inputs_runbook):
    """Inputs not in the environment are asked for by name and description, then used by the blocks."""
    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)], input="1.2.0\ns3cret\n")

    assert result.exit_code == 0
    assert result.output.startswith(
        "VERSION (The version being released, e.g. 1.2.0): 1.2.0\nPUBLISH_TOKEN (Token for the package index): \n"
    )
    lines = result.output.splitlines()
    assert '$ echo "Tagging 1.2.0"' in lines
    assert "Tagging 1.2.0" in lines
    assert '$ echo "Publishing 1.2.0 with $PUBLISH_TOKEN"' in lines
    assert "Publishing 1.2.0 with ****" in lines


def test_go_never_shows_a_secret_typed_at_its_prompt(runner, inputs_runbook):
    """A secret isn't echoed as it's typed, and a block printing it shows **** instead."""
    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)], input="1.2.0\ns3cret\n")

    assert result.exit_code == 0
    assert "s3cret" not in result.output


def test_go_uses_inputs_from_the_environment_without_prompting(runner, inputs_runbook, monkeypatch):
    """Inputs set in the environment aren't asked for."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")

    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)])

    assert result.exit_code == 0
    assert "VERSION (" not in result.output
    assert "PUBLISH_TOKEN (" not in result.output
    assert "Publishing 1.2.0 with ****" in result.output.splitlines()


def test_go_asks_again_when_an_answer_does_not_match_the_pattern(runner, inputs_runbook):
    """A typed answer that doesn't match its pattern is refused with the reason, and asked for again."""
    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)], input="latest\n1.2.0\ns3cret\n")

    assert result.exit_code == 0
    assert result.output.startswith(
        "VERSION (The version being released, e.g. 1.2.0): latest\n"
        "VERSION must match ^\\d+\\.\\d+\\.\\d+$\n"
        "VERSION (The version being released, e.g. 1.2.0): 1.2.0\n"
    )
    assert "Publishing 1.2.0 with ****" in result.output.splitlines()


def test_go_reports_an_environment_value_that_does_not_match_the_pattern(runner, inputs_runbook, monkeypatch):
    """A bad value from the environment stops go before anything runs, without a traceback."""
    monkeypatch.setenv("VERSION", "latest")

    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)], input="s3cret\n")

    assert result.exit_code == 1
    assert result.output == "Error: VERSION from the environment must match ^\\d+\\.\\d+\\.\\d+$\n"


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
    assert cli._duration(seconds) == expected
