"""Tests for CLI commands."""

import importlib.metadata
import re
import shutil
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


@pytest.fixture
def confirm_runbook(monkeypatch):
    """The docstring and confirm example runbook, with VERSION set in the environment so it isn't asked for."""
    monkeypatch.setenv("VERSION", "1.2.0")
    return RUNBOOKS / "docstring-and-confirm-example.md"


@pytest.fixture
def dry_runbook(tmp_path, monkeypatch):
    """A copy of the dry run example runbook in tmp_path, so a broken --dry can only write files there.

    Neither input is set in the environment.
    """
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("PUBLISH_TOKEN", raising=False)
    return Path(shutil.copy(RUNBOOKS / "dry-run-example.md", tmp_path))


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

    result = runner.invoke(cli.cli, ["go", str(path)], input="y\n")

    assert result.exit_code == 0
    assert re.sub(r"\(\d+\.\ds\)", "(Xs)", result.output) == textwrap.dedent(
        """\
        runbook.md
          1. Greet
          2. Again
        2 run blocks
        Start? [y/N] y

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

    result = runner.invoke(cli.cli, ["go", str(RUNBOOKS / "two_steps.md")], input="y\n")

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

    result = runner.invoke(cli.cli, ["go", str(path)], input="y\n")

    assert result.exit_code == 1
    assert "passing" in result.output.splitlines()
    assert re.search(r"^exit 3 \(\d+\.\ds\)$", result.output, re.MULTILINE)
    assert result.output.endswith('\nfinished: failed at "Fails" (exit 3)\n')
    assert "=== Never reached ===" not in result.output
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

    result = runner.invoke(cli.cli, ["go", str(path)], input="y\n")

    lines = result.output.splitlines()
    assert "$ echo '[bold]markup[/bold] :smile:'" in lines
    assert "[bold]markup[/bold] :smile:" in lines
    assert "0" * 200 in lines


def test_go_streams_output_line_by_line_through_a_pipe():
    """Each line is written as soon as the block prints it, even when paulrun's stdout is a pipe."""
    command = [sys.executable, "-c", "from paulrun.cli import cli; cli()", "go", str(RUNBOOKS / "two_steps.md")]
    arrivals: dict[str, float] = {}

    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as process:
        assert process.stdin is not None and process.stdout is not None  # set because both are pipes
        process.stdin.write("y\n")
        process.stdin.close()
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
    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)], input="1.2.0\ns3cret\ny\n")

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
    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)], input="1.2.0\ns3cret\ny\n")

    assert result.exit_code == 0
    assert "s3cret" not in result.output


def test_go_uses_inputs_from_the_environment_without_prompting(runner, inputs_runbook, monkeypatch):
    """Inputs set in the environment aren't asked for."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")

    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)], input="y\n")

    assert result.exit_code == 0
    assert "VERSION (" not in result.output
    assert "PUBLISH_TOKEN (" not in result.output
    assert "Publishing 1.2.0 with ****" in result.output.splitlines()


def test_go_asks_again_when_an_answer_does_not_match_the_pattern(runner, inputs_runbook):
    """A typed answer that doesn't match its pattern is refused with the reason, and asked for again."""
    result = runner.invoke(cli.cli, ["go", str(inputs_runbook)], input="latest\n1.2.0\ns3cret\ny\n")

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


def test_go_prints_docstrings_and_waits_at_confirms(runner, confirm_runbook):
    """Docstring and confirm text is printed with inputs substituted, and y at a confirm carries on."""
    result = runner.invoke(cli.cli, ["go", str(confirm_runbook)], input="y\ny\n")

    assert result.exit_code == 0
    assert re.sub(r"\(\d+\.\ds\)", "(Xs)", result.output) == textwrap.dedent(
        """\
        Docstring and confirm example
        inputs: VERSION=1.2.0
          1. Build
          2. Release on GitHub
        2 run blocks
        Start? [y/N] y

        === Build ===
        Building 1.2.0. This only echoes; nothing is built.
        $ echo "Built 1.2.0"
        Built 1.2.0
        exit 0 (Xs)

        === Release on GitHub ===
        Create a GitHub release for tag 1.2.0 and publish it.
        Continue? [y/N] y
        $ echo "Released 1.2.0"
        Released 1.2.0
        exit 0 (Xs)

        finished: ok (Xs)
        """
    )


@pytest.mark.parametrize("answer", ["n", "", "yes"])
def test_go_aborts_at_a_confirm_not_answered_y(runner, confirm_runbook, answer):
    """Any answer but y at a confirm ends the run there with exit code 1, naming the step."""
    result = runner.invoke(cli.cli, ["go", str(confirm_runbook)], input=f"y\n{answer}\n")

    assert result.exit_code == 1
    assert "Built 1.2.0" in result.output.splitlines()
    assert "Released 1.2.0" not in result.output.splitlines()
    assert result.output.endswith(f'Continue? [y/N] {answer}\n\nfinished: aborted at "Release on GitHub"\n')


@pytest.mark.parametrize("answer", ["n", "", "yes"])
def test_go_runs_nothing_when_the_start_prompt_is_not_answered_y(runner, confirm_runbook, answer):
    """Declining to start runs no steps and exits 1."""
    result = runner.invoke(cli.cli, ["go", str(confirm_runbook)], input=f"{answer}\n")

    assert result.exit_code == 1
    assert "===" not in result.output
    assert result.output.endswith(f"Start? [y/N] {answer}\n\nfinished: aborted before starting\n")


def test_go_overview_counts_one_run_block_in_the_singular(runner, tmp_path):
    """The overview says "1 run block", not "1 run blocks"."""
    path = write_runbook(tmp_path, "---\ntitle: One\n---\n\n## Only\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["go", str(path)], input="y\n")

    assert result.output.startswith("One\n  1. Only\n1 run block\nStart? [y/N] y\n")


def test_go_prints_docstring_and_confirm_text_verbatim(runner, tmp_path):
    """Text that looks like rich markup or emoji codes is printed exactly as written."""
    path = write_runbook(
        tmp_path,
        """\
        ## Verbatim

        ```docstring
        Run [bold]make[/bold] :smile:
        ```

        ```confirm
        Check [red]this[/red] :+1:
        ```
        """,
    )

    result = runner.invoke(cli.cli, ["go", str(path)], input="y\ny\n")

    lines = result.output.splitlines()
    assert "Run [bold]make[/bold] :smile:" in lines
    assert "Check [red]this[/red] :+1:" in lines


def test_go_dry_prints_every_block_filled_in_and_runs_nothing(runner, dry_runbook):
    """--dry asks only for plain inputs, shows every block with them filled in, and creates none of its files."""
    result = runner.invoke(cli.cli, ["go", "--dry", str(dry_runbook)], input="1.2.0\n")

    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        """\
        VERSION (The version being released, e.g. 1.2.0): 1.2.0
        Dry run example
        inputs: VERSION=1.2.0 PUBLISH_TOKEN=****
          1. Build
          2. Publish
        2 run blocks
        dry run: nothing will be run

        === Build ===
        $ echo "1.2.0" > built-1.2.0.txt

        === Publish ===
        Check built-1.2.0.txt before publishing.
        $ echo "published with $PUBLISH_TOKEN" > published-1.2.0.txt

        finished: dry run, nothing was run
        """
    )
    assert sorted(path.name for path in dry_runbook.parent.iterdir()) == ["dry-run-example.md"]


def test_go_dry_never_reads_or_shows_a_secret(runner, dry_runbook, monkeypatch):
    """A secret set in the environment is shown as **** and never appears in the output."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")

    result = runner.invoke(cli.cli, ["go", "--dry", str(dry_runbook)])

    assert result.exit_code == 0
    assert "inputs: VERSION=1.2.0 PUBLISH_TOKEN=****" in result.output.splitlines()
    assert "s3cret" not in result.output


def test_go_dry_still_rejects_a_bad_plain_input_from_the_environment(runner, dry_runbook, monkeypatch):
    """Plain inputs are checked under --dry exactly as in a real run."""
    monkeypatch.setenv("VERSION", "latest")

    result = runner.invoke(cli.cli, ["go", "--dry", str(dry_runbook)])

    assert result.exit_code == 1
    assert result.output == "Error: VERSION from the environment must match ^\\d+\\.\\d+\\.\\d+$\n"


def test_go_help_describes_dry(runner):
    """go --help lists --dry."""
    result = runner.invoke(cli.cli, ["go", "--help"])

    assert result.exit_code == 0
    assert "--dry" in result.output


def test_go_runs_python_blocks(runner, monkeypatch):
    """The python example's blocks run under Python, with inputs substituted and exported."""
    monkeypatch.setenv("VERSION", "1.2.0")

    result = runner.invoke(cli.cli, ["go", str(RUNBOOKS / "python-example.md")], input="y\n")

    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert "Releasing 1.2.0" in lines
    assert "Next version: 1.2.1" in lines


def test_go_stops_at_a_python_block_that_raises(runner, tmp_path):
    """A Python block that raises fails the run, naming its step, and later steps don't run."""
    path = write_runbook(
        tmp_path,
        """\
        ## Raises

        ```python run
        raise SystemExit("not today")
        ```

        ## Never reached

        ```sh run
        echo unreachable
        ```
        """,
    )

    result = runner.invoke(cli.cli, ["go", str(path)], input="y\n")

    assert result.exit_code == 1
    assert "not today" in result.output.splitlines()
    assert result.output.endswith('\nfinished: failed at "Raises" (exit 1)\n')
    assert "unreachable" not in result.output


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
