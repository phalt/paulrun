"""Tests for CLI commands."""

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import EntryPoint
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from rich.console import Console

from rundot import backends, cli
from rundot import runner as runner_module
from rundot import state as state_module
from rundot.backends import BackendError, Problem
from rundot.inputs import Input, InputError, NeedsHumanInput, collect
from rundot.runbook import parse
from tests.output import finished, normalized, overview, printed, title

RUNBOOKS = Path(__file__).parent / "runbooks"
LIBRARY = Path(__file__).parent / "library"


@pytest.fixture
def runner(monkeypatch):
    """Fixture providing a Click CLI test runner, with plain output even if the environment forces colour."""
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    return CliRunner()


@pytest.fixture(autouse=True)
def shellcheck_not_installed(without_shellcheck):
    """Output is the same whether or not shellcheck is installed. See without_shellcheck in conftest.py."""


def write_runbook(tmp_path: Path, text: str) -> Path:
    """Write a dedented runbook into tmp_path and return its path.

    run validates first and a title is required, so a runbook written without frontmatter gets `title: Test`.
    """
    text = textwrap.dedent(text)
    if not text.startswith("---\n"):
        text = "---\ntitle: Test\n---\n\n" + text
    path = tmp_path / "runbook.md"
    path.write_text(text)
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
def transcript_runbook(tmp_path, monkeypatch):
    """A copy of the transcript example runbook in tmp_path, away from started_in, where its transcript goes.

    Both inputs are set in the environment, so only the start prompt and the confirm are asked.
    """
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")
    return Path(shutil.copy(RUNBOOKS / "transcript-example.md", tmp_path))


@pytest.fixture
def input_block_runbook(tmp_path, monkeypatch):
    """A copy of the input block example in tmp_path, away from started_in, where its transcript goes.

    VERSION is set in the environment; PR and OTP aren't, so they're asked for at their blocks.
    """
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.delenv("PR", raising=False)
    monkeypatch.delenv("OTP", raising=False)
    return Path(shutil.copy(RUNBOOKS / "input-block-example.md", tmp_path))


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
    assert result.output == f"rundot, version {importlib.metadata.version('rundot')}\n"


def test_help_lists_run_command_and_says_a_runbook_can_go_first(runner):
    """--help lists run, and its usage shows a runbook can be given in place of a command."""
    result = runner.invoke(cli.cli, ["--help"])

    assert result.exit_code == 0
    assert "Usage: rundot [OPTIONS] RUNBOOK | COMMAND [ARGS]..." in result.output
    assert "\n  run " in result.output


def test_help_shows_the_header_version_and_links(runner):
    """--help opens with the rundot header, unwrapped, then the version and links to the docs and the project."""
    result = runner.invoke(cli.cli, ["--help"])

    assert result.exit_code == 0
    for line in cli.RUNDOT_HEADER.splitlines():
        assert f"\n  {line}\n" in result.output
    assert f"🔢 Version {importlib.metadata.version('rundot')}" in result.output
    assert "📚 Read the docs: https://docs.rundot.dev/" in result.output
    assert "🐙 Contribute on GitHub: https://github.com/phalt/rundot" in result.output


def test_rundot_with_nothing_else_shows_help(runner):
    """Bare rundot shows help, as it always has, rather than running or picking anything."""
    result = runner.invoke(cli.cli, [])

    assert result.exit_code == 0
    assert result.output == runner.invoke(cli.cli, ["--help"]).output


def test_a_runbook_runs_the_same_with_or_without_the_run_command(runner, started_in):
    """rundot RUNBOOK is rundot run RUNBOOK: same output, same exit code."""
    shutil.copy(RUNBOOKS / "two_steps.md", started_in)

    without_run = runner.invoke(cli.cli, ["two_steps.md"], input="y\n")
    with_run = runner.invoke(cli.cli, ["run", "two_steps.md"], input="y\n")

    assert without_run.exit_code == with_run.exit_code == 0, without_run.output
    assert normalized(without_run.output) == normalized(with_run.output)
    assert title(without_run.output) == "Two steps"


@pytest.mark.parametrize(
    "arguments",
    [["say-where", "--dry"], ["--dry", "say-where"], ["run", "--dry", "say-where"]],
    ids=["option after", "option before", "with run"],
)
def test_options_work_on_either_side_of_a_runbook_given_without_run(arguments, runner, monkeypatch):
    """--dry and --step can come before or after the runbook, with or without run."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, arguments)

    assert result.exit_code == 0, result.output
    assert finished(result.output) == "dry run, nothing was run"


def test_a_runbook_given_without_run_has_the_same_errors(runner, empty_library):
    """A runbook that isn't there is the same usage error, with or without run."""
    result = runner.invoke(cli.cli, ["rebuild-frontend"])

    assert result.exit_code == 2
    assert f"no rebuild-frontend.md in the library at {empty_library}" in result.output


def test_go_is_not_a_command_any_more(runner, empty_library):
    """go was replaced by run, so rundot go x looks for a runbook called go, and doesn't run x."""
    shutil.copy(RUNBOOKS / "two_steps.md", empty_library)

    result = runner.invoke(cli.cli, ["go", "two_steps"], input="y\n")

    assert result.exit_code == 2
    assert "no runbook 'go'" in result.output
    assert "\n  go " not in runner.invoke(cli.cli, ["--help"]).output


@pytest.mark.parametrize("command", ["check", "inputs", "library", "backends", "run"])
def test_a_command_name_is_never_read_as_a_runbook(command, runner, monkeypatch, tmp_path):
    """Command names win, so a book named after a command doesn't stop the command working."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / f"{command}.md").write_text(
        "---\ntitle: A book named like a command\n---\n\n## S\n\n```sh run\necho book\n```\n"
    )

    result = runner.invoke(cli.cli, [command, "--help"])

    assert result.exit_code == 0
    assert f"Usage: rundot {command} " in result.output


def test_run_reaches_a_book_named_like_a_command(runner, monkeypatch, tmp_path):
    """rundot run check runs the book check.md, since rundot check is the command."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "check.md").write_text(
        "---\ntitle: Check the deploy\n---\n\n## S\n\n```sh run\necho the book ran\n```\n"
    )

    result = runner.invoke(cli.cli, ["run", "check"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "the book ran" in printed(result.output)


def test_run_prints_the_directory_blocks_run_in_after_the_title(runner, tmp_path, started_in):
    """run names the directory it was started in straight after the title, so you see where blocks will run."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")

    for arguments in (["run", str(path)], ["run", "--dry", str(path)]):
        result = runner.invoke(cli.cli, arguments, input="y\n")

        assert result.exit_code == 0
        assert title(result.output) == "Test"
        assert next(iter(overview(result.output))) == "directory"
        assert "".join(overview(result.output)["directory"]) == str(started_in)


def test_run_prints_each_step_block_and_result(runner, tmp_path, started_in):
    """run boxes the overview, rules off each step, brackets each block's output and result, and boxes how it ended."""
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

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 0
    assert normalized(result.output) == textwrap.dedent(
        """\
        ╭─ Test ─╮
        │ directory  DIR │
        │ steps      1. Greet │
        │            2. Again │
        │ blocks     2 run blocks │
        ╰─╯
        Start? [y/N] y

        1/2  Greet ━

          ┌ sh · 10:02:13.482
          │ hello
          │ world
          └ ✓ exit 0 · Xs

        2/2  Again ━

          ┌ sh · 10:02:13.482
          │ again
          └ ✓ exit 0 · Xs

        ╭─╮
        │ ✓ finished ok · Xs │
        ╰─╯
        """
    )


def test_run_shows_a_directory_too_long_for_the_box_in_full(runner, tmp_path, monkeypatch):
    """A long path, like macOS's temporary directories, carries on over more rows rather than being cut short."""
    deep = tmp_path / ("a-very-long-directory-name-" * 4) / "and-then-some-more"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 0
    assert "…" not in result.output
    assert len(overview(result.output)["directory"]) > 1
    assert "".join(overview(result.output)["directory"]) == str(deep)
    assert all(len(line) <= 80 for line in result.output.splitlines())


def test_run_runs_blocks_in_the_directory_it_is_started_from(runner, started_in):
    """Blocks run where rundot is started, not in the runbook's directory, and can still find the runbook's."""
    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "two_steps.md")], input="y\n")

    assert result.exit_code == 0
    lines = printed(result.output)
    assert ["1", "2", "3"] == [line for line in lines if line in {"1", "2", "3"}]
    assert str(started_in.resolve()) in lines
    assert f"runbook: {RUNBOOKS.resolve()}" in lines


def test_run_closes_the_bracket_of_a_block_that_prints_nothing_straight_away(runner, tmp_path):
    """A block that prints nothing is just its heading and its result."""
    path = write_runbook(tmp_path, "## Quiet\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 0
    assert "\n  ┌ sh · 10:02:13.482\n  └ ✓ exit 0 · Xs\n" in normalized(result.output)


def test_run_hides_code_unless_asked_to_show_it(runner, tmp_path):
    """Code is left out by default. --show-code puts it in the bracket, in front of the output."""
    path = write_runbook(tmp_path, "## Greet\n\n```sh run\necho hello\n\necho world\n```\n")

    hidden = runner.invoke(cli.cli, ["run", str(path)], input="y\n")
    shown = runner.invoke(cli.cli, ["run", "--show-code", str(path)], input="y\n")

    assert hidden.exit_code == shown.exit_code == 0
    assert "\n  ┌ sh · 10:02:13.482\n  │ hello\n  │ world\n  └ ✓ exit 0 · Xs\n" in normalized(hidden.output)
    # A blank line of code is a bare │, so nothing ends in whitespace.
    assert (
        "\n  ┌ sh · 10:02:13.482\n  │ echo hello\n  │\n  │ echo world\n  ├ output\n  │ hello\n  │ world\n"
        "  └ ✓ exit 0 · Xs\n"
    ) in normalized(shown.output)


def test_run_marks_stderr_with_a_red_bar_and_leaves_the_line_plain():
    """In colour, a line a block wrote to stderr has a red │, and the line itself is the normal colour."""
    console = cli.Console(force_terminal=True, color_system="standard", width=80, record=True)
    printer = cli._Printer(console)

    printer(runner_module.OutputLine("fine"))
    printer(runner_module.OutputLine("broken", stderr=True))

    out, err = console.export_text(styles=True).splitlines()
    assert out == "\x1b[2m  │\x1b[0m fine"
    assert err == "\x1b[31m  │\x1b[0m broken"


def test_run_shows_a_blank_line_of_output_as_a_bare_bar(runner, tmp_path):
    """A blank line a block prints keeps its place, without trailing whitespace."""
    path = write_runbook(tmp_path, "## Gap\n\n```sh run\necho a\necho\necho b\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert "\n  │ a\n  │\n  │ b\n" in result.output


def test_run_stops_at_the_failing_block_and_names_its_step(runner, tmp_path):
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

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 1
    assert "passing" in printed(result.output)
    assert "\n  └ ✗ exit 3 · Xs\n" in normalized(result.output)
    assert finished(normalized(result.output)) == '✗ failed at "Fails" (exit 3) · Xs'
    assert "3/3  Never reached" not in result.output
    assert "unreachable" not in result.output


def test_run_prints_output_and_code_verbatim(runner, tmp_path):
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

    result = runner.invoke(cli.cli, ["run", "--show-code", str(path)], input="y\n")

    lines = printed(result.output)
    assert "echo '[bold]markup[/bold] :smile:'" in lines
    assert "[bold]markup[/bold] :smile:" in lines
    assert "0" * 200 in lines


def test_run_streams_output_line_by_line_through_a_pipe():
    """Each line is written as soon as the block prints it, even when rundot's stdout is a pipe."""
    command = [sys.executable, "-c", "from rundot.cli import cli; cli()", "run", str(RUNBOOKS / "two_steps.md")]
    arrivals: dict[str, float] = {}

    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as process:
        assert process.stdin is not None and process.stdout is not None  # set because both are pipes
        process.stdin.write("y\n")
        process.stdin.close()
        for line in process.stdout:
            arrivals.setdefault(line.removesuffix("\n").removeprefix("  │ "), time.monotonic())

    assert process.returncode == 0
    assert arrivals["3"] - arrivals["1"] >= 0.3


def test_run_rejects_missing_runbook_as_usage_error(runner, tmp_path):
    """A runbook path that doesn't exist is a usage error."""
    result = runner.invoke(cli.cli, ["run", str(tmp_path / "missing.md")])

    assert result.exit_code == 2


@pytest.mark.parametrize("name", ["say-where", "say-where.md"])
def test_run_runs_a_book_from_the_library_by_name_where_it_was_started(name, runner, monkeypatch, started_in):
    """A name that isn't a file here is the book of that name in RUNDOT_LIBRARY, and runs here, not in the library."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["run", name], input="y\n")

    assert result.exit_code == 0, result.output
    assert title(result.output) == "Say where"
    lines = printed(result.output)
    assert str(started_in.resolve()) in lines
    assert f"kept in: {LIBRARY.resolve()}" in lines


@pytest.mark.parametrize("command", ["check", "inputs"])
@pytest.mark.parametrize("name", ["update-project-deps", "update-project-deps.md"])
def test_check_and_inputs_find_a_book_in_the_library_by_name(command, name, runner, monkeypatch):
    """check and inputs look up a name the same way run does."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, [command, name])

    assert result.exit_code == 0, result.output
    assert ("BRANCH" if command == "inputs" else "ok") in result.output


def test_check_names_a_book_by_its_path_in_the_library(runner, monkeypatch):
    """check's report says which file it checked, so a book is shown by where it's kept."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["check", "say-where"])

    assert result.output == f"{LIBRARY / 'say-where.md'}: ok\n"


def test_run_uses_the_default_library_in_the_home_directory(runner, tmp_path, monkeypatch):
    """With no RUNDOT_LIBRARY, a name is looked up in ~/runbooks."""
    monkeypatch.delenv("RUNDOT_LIBRARY")
    monkeypatch.setenv("HOME", str(tmp_path))
    shutil.copytree(LIBRARY, tmp_path / "runbooks")

    result = runner.invoke(cli.cli, ["check", "say-where"])

    assert result.output == f"{tmp_path / 'runbooks' / 'say-where.md'}: ok\n"


def test_run_runs_a_file_here_before_a_book_with_the_same_name(runner, monkeypatch, started_in):
    """Paths win over names: a runbook where rundot is started is used, not the library's book."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))
    write_runbook(started_in, "## Here\n\n```sh run\necho the local one\n```\n").rename(started_in / "say-where.md")

    result = runner.invoke(cli.cli, ["run", "say-where.md"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "the local one" in printed(result.output)


def test_run_never_looks_in_the_library_for_a_path(runner, monkeypatch):
    """An argument with a / is only a path, so a mistyped path is an error, not a different runbook."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["run", "docs/say-where.md"])

    assert result.exit_code == 2
    # Click names run's optional RUNBOOK '[RUNBOOK]', so only the message after it is checked.
    assert "': no such file: docs/say-where.md\n" in result.output


@pytest.mark.parametrize("command", ["run", "check", "inputs"])
def test_a_name_that_is_not_here_or_in_the_library_is_a_usage_error(command, runner, empty_library):
    """The error names both places rundot looked, so it's clear which one to fix."""
    result = runner.invoke(cli.cli, [command, "rebuild-frontend"])

    assert result.exit_code == 2
    # Click names run's optional RUNBOOK '[RUNBOOK]', so only the message after it is checked.
    assert (
        "': no runbook 'rebuild-frontend': no such file here, "
        f"and no rebuild-frontend.md in the library at {empty_library}\n"
    ) in result.output


def test_run_reports_runbook_it_cannot_read(runner, tmp_path):
    """A runbook that can't be parsed is reported as an error, without a traceback."""
    path = write_runbook(tmp_path, "---\ntitle: Unclosed\n\n## Step\n")

    result = runner.invoke(cli.cli, ["run", str(path)])

    assert result.exit_code == 1
    assert result.output == "Error: frontmatter has no closing ---\n"


def test_run_refuses_to_start_a_runbook_with_errors(runner, tmp_path):
    """run checks the runbook first, and any error stops it before inputs are asked for or anything runs."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Broken
        inputs:
          - name: VERSION
            description: The version
        ---

        ## Step

        ```sh run
        touch ran
        ```

        ```cobol run
        DISPLAY '<VERSION>'.
        ```
        """,
    )

    result = runner.invoke(cli.cli, ["run", str(path)], input="1.2.0\ny\n")

    assert result.exit_code == 1
    assert result.output == f"{path}:14: error: no backend runs 'cobol' blocks\n\n1 error\n"
    assert not (tmp_path / "ran").exists()


def test_run_dry_also_refuses_a_runbook_with_errors(runner, tmp_path):
    """--dry checks the runbook the same way, so a dry run can't hide a broken block."""
    path = write_runbook(tmp_path, "## Step\n\n```sh run\nif true; then\nfi\n```\n")

    result = runner.invoke(cli.cli, ["run", "--dry", str(path)])

    assert result.exit_code == 1
    assert result.output == f"{path}:9: error: syntax error near unexpected token `fi'\n\n1 error\n"


def test_run_prints_warnings_and_carries_on(runner, tmp_path):
    """Warnings are printed before the run, but don't stop it."""
    path = write_runbook(tmp_path, "---\ntitle: Warns\nextra: 1\n---\n\n## Step\n\n```sh run\necho ran\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 0
    assert result.output.startswith(f"{path}:3: warning: unknown frontmatter key 'extra'\n\n1 warning\n╭─ Warns ")
    assert "ran" in printed(result.output)


def test_check_passes_a_valid_runbook(runner):
    """check exits 0 and says so for a runbook with no problems."""
    path = RUNBOOKS / "all_features.md"

    result = runner.invoke(cli.cli, ["check", str(path)])

    assert result.exit_code == 0
    assert result.output == f"{path}: ok\n"


@pytest.mark.parametrize("fixture", sorted(path.name for path in (RUNBOOKS / "broken").glob("*.md")))
def test_check_fails_every_broken_fixture(runner, fixture):
    """check exits 1 on each broken fixture, reporting its error with file and line."""
    path = RUNBOOKS / "broken" / fixture

    result = runner.invoke(cli.cli, ["check", str(path)])

    assert result.exit_code == 1
    assert re.match(rf"{re.escape(str(path))}:\d+: error: ", result.output)
    assert result.output.endswith("\n\n1 error\n")


def test_check_prints_every_finding_with_a_summary(runner, tmp_path):
    """Every error and warning is listed in line order, then how many of each there were."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Several
        extra: 1
        ---

        ## Step

        ```sh run
        echo <ONE> <TWO>
        ```
        """,
    )

    result = runner.invoke(cli.cli, ["check", str(path)])

    assert result.exit_code == 1
    assert result.output == (
        f"{path}:3: warning: unknown frontmatter key 'extra'\n"
        f"{path}:9: error: <ONE> isn't a declared input\n"
        f"{path}:9: error: <TWO> isn't a declared input\n"
        "\n"
        "2 errors, 1 warning\n"
    )


def test_check_passes_a_runbook_with_only_warnings(runner, tmp_path):
    """Warnings are printed, but check still exits 0."""
    path = write_runbook(tmp_path, "---\ntitle: Warns\nextra: 1\nmore: 2\n---\n\n## Step\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["check", str(path)])

    assert result.exit_code == 0
    assert result.output.endswith("\n\n2 warnings\n")


def test_check_prints_messages_verbatim(runner, tmp_path):
    """A message quoting rich-markup-like text, such as a pattern with [brackets], is printed as it is."""
    path = write_runbook(
        tmp_path, "---\ntitle: T\ninputs:\n  - name: V\n    description: v\n    pattern: '[bold'\n---\n\n## S\n"
    )

    result = runner.invoke(cli.cli, ["check", str(path)])

    assert "input V's pattern isn't a valid regex: unterminated character set at position 0" in result.output


def test_check_reports_a_runbook_it_cannot_read(runner, tmp_path):
    """A runbook check can't parse is an error, without a traceback."""
    path = write_runbook(tmp_path, "---\ntitle: Unclosed\n\n## Step\n")

    result = runner.invoke(cli.cli, ["check", str(path)])

    assert result.exit_code == 1
    assert result.output == "Error: frontmatter has no closing ---\n"


def test_check_reports_backends_that_cannot_load(runner, tmp_path, monkeypatch):
    """If the installed backends conflict, check says so instead of crashing."""

    def conflicting_backends():
        raise BackendError("language 'sh' is claimed by both 'shell' and 'rival'")

    monkeypatch.setattr(cli, "load_backends", conflicting_backends)

    result = runner.invoke(cli.cli, ["check", str(RUNBOOKS / "minimal.md")])

    assert result.exit_code == 1
    assert result.output == "Error: language 'sh' is claimed by both 'shell' and 'rival'\n"


def test_help_lists_check_command(runner):
    """--help lists the check command."""
    result = runner.invoke(cli.cli, ["--help"])

    assert "\n  check " in result.output


def test_run_reports_backends_that_cannot_load(runner, tmp_path, monkeypatch):
    """If the installed backends conflict, run says so instead of crashing."""

    def conflicting_backends():
        raise BackendError("language 'sh' is claimed by both 'shell' and 'rival'")

    monkeypatch.setattr(cli, "load_backends", conflicting_backends)
    path = write_runbook(tmp_path, "## Step\n\n```sh run\necho hi\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)])

    assert result.exit_code == 1
    assert result.output == "Error: language 'sh' is claimed by both 'shell' and 'rival'\n"


def test_run_prompts_for_inputs_and_uses_the_answers(runner, inputs_runbook):
    """Inputs not in the environment are asked for by name and description, then used by the blocks."""
    result = runner.invoke(cli.cli, ["run", "--show-code", str(inputs_runbook)], input="1.2.0\ns3cret\ny\n")

    assert result.exit_code == 0
    assert result.output.startswith(
        "VERSION (The version being released, e.g. 1.2.0): 1.2.0\nPUBLISH_TOKEN (Token for the package index): \n"
    )
    lines = printed(result.output)
    assert 'echo "Tagging 1.2.0"' in lines
    assert "Tagging 1.2.0" in lines
    assert 'echo "Publishing 1.2.0 with $PUBLISH_TOKEN"' in lines
    assert "Publishing 1.2.0 with ****" in lines


def test_run_shows_an_inputs_default_and_takes_it_when_enter_is_pressed(runner, monkeypatch):
    """The prompt shows the default in brackets, and an empty answer uses it."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.delenv("BRANCH", raising=False)

    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "default-example.md")], input="\ny\n")

    assert result.exit_code == 0, result.output
    assert result.output.startswith("BRANCH (The branch to release from) [main]: \n")
    assert "Releasing 1.2.0 from main" in printed(result.output)


def test_run_uses_an_answer_typed_over_the_default(runner, monkeypatch):
    """Typing an answer replaces the default."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.delenv("BRANCH", raising=False)

    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "default-example.md")], input="release\ny\n")

    assert result.exit_code == 0, result.output
    assert "Releasing 1.2.0 from release" in printed(result.output)


def test_run_uses_the_environment_over_a_default_without_asking(runner, monkeypatch):
    """BRANCH set in the environment is used, and BRANCH isn't asked for."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("BRANCH", "release")

    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "default-example.md")], input="y\n")

    assert result.exit_code == 0, result.output
    assert "BRANCH (" not in result.output
    assert "Releasing 1.2.0 from release" in printed(result.output)


def test_run_shows_a_default_in_an_input_block_prompt(runner, tmp_path):
    """An input block's default is shown and used the same way."""
    path = write_runbook(
        tmp_path,
        "## Merge\n\n```input\nname: BASE\ndescription: The branch to merge into\ndefault: main\n```\n\n"
        "```sh run\necho merging into <BASE>\n```\n",
    )

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n\n")

    assert result.exit_code == 0, result.output
    assert "BASE (The branch to merge into) [main]: " in result.output
    assert "merging into main" in printed(result.output)


def test_run_lists_an_inputs_choices_and_asks_again_for_an_answer_outside_them(runner, monkeypatch):
    """The prompt lists the choices, and an answer that isn't one gets why and the question again."""
    monkeypatch.delenv("FE_SET", raising=False)

    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "choices-example.md")], input="everything\nbilling\ny\n")

    assert result.exit_code == 0, result.output
    assert result.output.startswith(
        "FE_SET (Which frontend set to rebuild) [comms] (comms, billing, all): everything\n"
        "FE_SET must be one of: comms, billing, all\n"
        "FE_SET (Which frontend set to rebuild) [comms] (comms, billing, all): billing\n"
    )
    assert "Rebuilding the billing frontend" in printed(result.output)


def test_run_takes_a_default_that_is_one_of_the_choices(runner, monkeypatch):
    """Pressing enter gives the default, which is one of the choices."""
    monkeypatch.delenv("FE_SET", raising=False)

    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "choices-example.md")], input="\ny\n")

    assert result.exit_code == 0, result.output
    assert "Rebuilding the comms frontend" in printed(result.output)


def test_run_stops_for_an_environment_value_that_is_not_one_of_the_choices(runner, monkeypatch, started_in):
    """A value from the environment outside the choices stops the run before anything runs."""
    monkeypatch.setenv("FE_SET", "everything")

    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "choices-example.md")])

    assert result.exit_code == 1
    assert result.output == "Error: FE_SET from the environment must be one of: comms, billing, all\n"


def test_run_lists_choices_for_an_input_block(runner, tmp_path):
    """An input block's choices are listed and checked the same way."""
    path = write_runbook(
        tmp_path,
        "## Deploy\n\n```input\nname: ENV\ndescription: Where to deploy\nchoices: [staging, prod]\n```\n\n"
        "```sh run\necho deploying to <ENV>\n```\n",
    )

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\nqa\nprod\n")

    assert result.exit_code == 0, result.output
    assert "ENV (Where to deploy) (staging, prod): qa\nENV must be one of: staging, prod\n" in result.output
    assert "deploying to prod" in printed(result.output)


def test_run_never_shows_a_secret_typed_at_its_prompt(runner, inputs_runbook):
    """A secret isn't echoed as it's typed, and a block printing it shows **** instead."""
    result = runner.invoke(cli.cli, ["run", str(inputs_runbook)], input="1.2.0\ns3cret\ny\n")

    assert result.exit_code == 0
    assert "s3cret" not in result.output


def test_run_uses_inputs_from_the_environment_without_prompting(runner, inputs_runbook, monkeypatch):
    """Inputs set in the environment aren't asked for."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")

    result = runner.invoke(cli.cli, ["run", str(inputs_runbook)], input="y\n")

    assert result.exit_code == 0
    assert "VERSION (" not in result.output
    assert "PUBLISH_TOKEN (" not in result.output
    assert "Publishing 1.2.0 with ****" in printed(result.output)


def test_run_asks_again_when_an_answer_does_not_match_the_pattern(runner, inputs_runbook):
    """A typed answer that doesn't match its pattern is refused with the reason, and asked for again."""
    result = runner.invoke(cli.cli, ["run", str(inputs_runbook)], input="latest\n1.2.0\ns3cret\ny\n")

    assert result.exit_code == 0
    assert result.output.startswith(
        "VERSION (The version being released, e.g. 1.2.0): latest\n"
        "VERSION must match ^\\d+\\.\\d+\\.\\d+$\n"
        "VERSION (The version being released, e.g. 1.2.0): 1.2.0\n"
    )
    assert "Publishing 1.2.0 with ****" in printed(result.output)


def test_run_reports_an_environment_value_that_does_not_match_the_pattern(runner, inputs_runbook, monkeypatch):
    """A bad value from the environment stops run before anything runs, without a traceback."""
    monkeypatch.setenv("VERSION", "latest")

    result = runner.invoke(cli.cli, ["run", str(inputs_runbook)], input="s3cret\n")

    assert result.exit_code == 1
    assert result.output == "Error: VERSION from the environment must match ^\\d+\\.\\d+\\.\\d+$\n"


def test_run_prints_docstrings_and_waits_at_confirms(runner, confirm_runbook, started_in):
    """Docstring and confirm text is printed with inputs substituted, and y at a confirm carries on."""
    result = runner.invoke(cli.cli, ["run", str(confirm_runbook)], input="y\ny\n")

    assert result.exit_code == 0
    assert normalized(result.output) == textwrap.dedent(
        """\
        ╭─ Docstring and confirm example ─╮
        │ directory  DIR │
        │ inputs     VERSION=1.2.0 │
        │ steps      1. Build │
        │            2. Release on GitHub │
        │ blocks     2 run blocks │
        ╰─╯
        Start? [y/N] y

        1/2  Build ━
          Building 1.2.0. This only echoes; nothing is built.

          ┌ sh · 10:02:13.482
          │ Built 1.2.0
          └ ✓ exit 0 · Xs

        2/2  Release on GitHub ━
        ╭─ confirm ─╮
        │ Create a GitHub release for tag 1.2.0 and publish it. │
        ╰─╯
        Continue? [y/N] y

          ┌ sh · 10:02:13.482
          │ Released 1.2.0
          └ ✓ exit 0 · Xs

        ╭─╮
        │ ✓ finished ok · Xs │
        ╰─╯
        """
    )


@pytest.mark.parametrize("answer", ["n", "", "yes"])
def test_run_aborts_at_a_confirm_not_answered_y(runner, confirm_runbook, answer):
    """Any answer but y at a confirm ends the run there with exit code 1, naming the step."""
    result = runner.invoke(cli.cli, ["run", str(confirm_runbook)], input=f"y\n{answer}\n")

    assert result.exit_code == 1
    assert "Built 1.2.0" in printed(result.output)
    assert "Released 1.2.0" not in printed(result.output)
    assert normalized(result.output).endswith(
        f'Continue? [y/N] {answer}\n\n╭─╮\n│ ✗ aborted at "Release on GitHub" │\n╰─╯\n'
    )


@pytest.mark.parametrize("answer", ["n", "", "yes"])
def test_run_runs_nothing_when_the_start_prompt_is_not_answered_y(runner, confirm_runbook, answer):
    """Declining to start runs no steps and exits 1."""
    result = runner.invoke(cli.cli, ["run", str(confirm_runbook)], input=f"{answer}\n")

    assert result.exit_code == 1
    assert "===" not in result.output
    assert normalized(result.output).endswith(f"Start? [y/N] {answer}\n\n╭─╮\n│ ✗ aborted before starting │\n╰─╯\n")


def test_run_overview_counts_one_run_block_in_the_singular(runner, tmp_path, started_in):
    """The overview says "1 run block", not "1 run blocks"."""
    path = write_runbook(tmp_path, "---\ntitle: One\n---\n\n## Only\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert normalized(result.output).startswith(
        "╭─ One ─╮\n│ directory  DIR │\n│ steps      1. Only │\n│ blocks     1 run block │\n╰─╯\nStart? [y/N] y\n"
    )


def test_run_prints_docstring_and_confirm_text_verbatim(runner, tmp_path):
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

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\ny\n")

    lines = result.output.splitlines()
    assert "  Run [bold]make[/bold] :smile:" in lines
    assert "│ Check [red]this[/red] :+1: │" in lines


def test_run_dry_prints_every_block_filled_in_and_runs_nothing(runner, dry_runbook, started_in):
    """--dry asks only for plain inputs, shows every block with them filled in, and creates none of its files."""
    result = runner.invoke(cli.cli, ["run", "--dry", str(dry_runbook)], input="1.2.0\n")

    assert result.exit_code == 0
    assert normalized(result.output) == textwrap.dedent(
        """\
        VERSION (The version being released, e.g. 1.2.0): 1.2.0
        ╭─ Dry run example ─╮
        │ directory  DIR │
        │ inputs     VERSION=1.2.0 PUBLISH_TOKEN=**** │
        │ steps      1. Build │
        │            2. Publish │
        │ blocks     2 run blocks │
        ╰─╯
        dry run: nothing will be run

        1/2  Build ━

          ┌ sh
          │ echo "1.2.0" > built-1.2.0.txt
          └ not run

        2/2  Publish ━
        ╭─ confirm ─╮
        │ Check built-1.2.0.txt before publishing. │
        ╰─╯

          ┌ sh
          │ echo "published with $PUBLISH_TOKEN" > published-1.2.0.txt
          └ not run

        ╭─╮
        │ dry run, nothing was run │
        ╰─╯
        """
    )
    assert sorted(path.name for path in dry_runbook.parent.iterdir()) == ["dry-run-example.md"]


def test_run_dry_never_reads_or_shows_a_secret(runner, dry_runbook, monkeypatch):
    """A secret set in the environment is shown as **** and never appears in the output."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")

    result = runner.invoke(cli.cli, ["run", "--dry", str(dry_runbook)])

    assert result.exit_code == 0
    assert "│ inputs     VERSION=1.2.0 PUBLISH_TOKEN=**** │" in normalized(result.output).splitlines()
    assert "s3cret" not in result.output


def test_run_dry_still_rejects_a_bad_plain_input_from_the_environment(runner, dry_runbook, monkeypatch):
    """Plain inputs are checked under --dry exactly as in a real run."""
    monkeypatch.setenv("VERSION", "latest")

    result = runner.invoke(cli.cli, ["run", "--dry", str(dry_runbook)])

    assert result.exit_code == 1
    assert result.output == "Error: VERSION from the environment must match ^\\d+\\.\\d+\\.\\d+$\n"


def test_run_step_runs_skips_and_quits_block_by_block(runner, started_in):
    """--step asks after each run block's code: y runs it, s skips it, and q ends the run there with exit 1."""
    result = runner.invoke(cli.cli, ["run", "--step", str(RUNBOOKS / "step-example.md")], input="y\ny\ns\nq\n")

    assert result.exit_code == 1
    assert normalized(result.output) == textwrap.dedent(
        """\
        ╭─ Step example ─╮
        │ directory  DIR │
        │ steps      1. Build │
        │            2. Publish │
        │            3. Announce │
        │ blocks     3 run blocks │
        ╰─╯
        Start? [y/N] y

        1/3  Build ━

          ┌ sh · 10:02:13.482
          ├ Run this block? [y]es / [s]kip / [q]uit y
          │ Building
          └ ✓ exit 0 · Xs

        2/3  Publish ━

          ┌ sh · 10:02:13.482
          ├ Run this block? [y]es / [s]kip / [q]uit s
          └ ↷ skipped

        3/3  Announce ━

          ┌ sh · 10:02:13.482
          ├ Run this block? [y]es / [s]kip / [q]uit q
          └ not run

        ╭─╮
        │ ✗ aborted at "Announce" │
        ╰─╯
        """
    )


def test_run_step_finishes_ok_when_blocks_are_only_skipped(runner):
    """Skipping isn't failing: a run where every block is skipped still exits 0."""
    result = runner.invoke(cli.cli, ["run", "--step", str(RUNBOOKS / "step-example.md")], input="y\ns\ns\ns\n")

    assert result.exit_code == 0
    assert result.output.splitlines().count("  └ ↷ skipped") == 3
    assert "Building" not in result.output.splitlines()


def test_run_step_asks_again_after_an_answer_it_does_not_know(runner):
    """An answer other than y, s or q gets the question again."""
    result = runner.invoke(cli.cli, ["run", "--step", str(RUNBOOKS / "step-example.md")], input="y\nmaybe\n\nq\n")

    assert result.exit_code == 1
    assert result.output.count("Run this block? [y]es / [s]kip / [q]uit") == 3


def test_run_dry_step_behaves_exactly_like_dry(runner, dry_runbook):
    """--step is ignored with --dry: same output, nothing asked, nothing run."""
    dry = runner.invoke(cli.cli, ["run", "--dry", str(dry_runbook)], input="1.2.0\n")
    dry_step = runner.invoke(cli.cli, ["run", "--dry", "--step", str(dry_runbook)], input="1.2.0\n")

    assert dry_step.exit_code == 0
    assert dry_step.output == dry.output
    assert sorted(path.name for path in dry_runbook.parent.iterdir()) == ["dry-run-example.md"]


def test_run_steps_through_a_runbook_with_step_in_its_frontmatter(runner, started_in):
    """step: true asks before each run block without --step being given, the same as --step."""
    path = RUNBOOKS / "step-frontmatter-example.md"

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\ns\ny\n")
    with_flag = runner.invoke(cli.cli, ["run", "--step", str(path)], input="y\ns\ny\n")

    assert result.exit_code == 0, result.output
    assert result.output == with_flag.output
    assert normalized(result.output) == textwrap.dedent(
        """\
        ╭─ Step frontmatter example ─╮
        │ directory  DIR │
        │ steps      1. Migrate the database │
        │            2. Restart the service │
        │ blocks     2 run blocks │
        ╰─╯
        Start? [y/N] y

        1/2  Migrate the database ━

          ┌ sh · 10:02:13.482
          ├ Run this block? [y]es / [s]kip / [q]uit s
          └ ↷ skipped

        2/2  Restart the service ━

          ┌ sh · 10:02:13.482
          ├ Run this block? [y]es / [s]kip / [q]uit y
          │ Restarting
          └ ✓ exit 0 · Xs

        ╭─╮
        │ ✓ finished ok · Xs │
        ╰─╯
        """
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["run", "--no-step", "step-frontmatter-example"],
        ["--no-step", "step-frontmatter-example"],
        ["step-frontmatter-example", "--no-step"],
    ],
    ids=["with run", "option before", "option after"],
)
def test_no_step_runs_a_runbook_with_step_in_its_frontmatter_straight_through(arguments, runner, monkeypatch):
    """--no-step overrides step: true, so every block runs without being asked about, wherever the option goes."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(RUNBOOKS))

    result = runner.invoke(cli.cli, arguments, input="y\n")

    assert result.exit_code == 0, result.output
    assert "Run this block?" not in result.output
    assert {"Migrating", "Restarting"} <= set(printed(result.output))
    assert finished(result.output).startswith("✓ finished ok")


def test_no_step_does_nothing_to_a_runbook_without_step(runner):
    """--no-step is how every runbook without step: true already runs."""
    path = str(RUNBOOKS / "two_steps.md")

    plain = runner.invoke(cli.cli, ["run", path], input="y\n")
    no_step = runner.invoke(cli.cli, ["run", "--no-step", path], input="y\n")

    assert no_step.exit_code == 0, no_step.output
    assert normalized(no_step.output) == normalized(plain.output)


def test_dry_ignores_step_in_the_frontmatter(runner):
    """Nothing runs under --dry, so step: true asks nothing, as --step does."""
    result = runner.invoke(cli.cli, ["run", "--dry", str(RUNBOOKS / "step-frontmatter-example.md")])

    assert result.exit_code == 0, result.output
    assert "Run this block?" not in result.output
    assert finished(result.output) == "dry run, nothing was run"


def test_run_help_describes_step(runner):
    """run --help lists --step and --no-step, and says --no-step overrides the frontmatter."""
    result = runner.invoke(cli.cli, ["run", "--help"])

    assert "--step / --no-step" in result.output
    assert "step: true" in result.output


def test_run_help_describes_show_code(runner):
    """run --help lists --show-code, and says --dry always shows code."""
    result = runner.invoke(cli.cli, ["run", "--help"])

    assert "--show-code" in result.output
    assert "--dry always shows it." in " ".join(result.output.split())


def test_run_help_describes_dry(runner):
    """run --help lists --dry."""
    result = runner.invoke(cli.cli, ["run", "--help"])

    assert result.exit_code == 0
    assert "--dry" in result.output


def test_run_runs_python_blocks(runner, monkeypatch):
    """The python example's blocks run under Python, with inputs substituted and exported."""
    monkeypatch.setenv("VERSION", "1.2.0")

    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "python-example.md")], input="y\n")

    assert result.exit_code == 0
    lines = printed(result.output)
    assert "Releasing 1.2.0" in lines
    assert "Next version: 1.2.1" in lines


def test_run_stops_at_a_python_block_that_raises(runner, tmp_path):
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

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 1
    assert "not today" in printed(result.output)
    assert finished(normalized(result.output)) == '✗ failed at "Raises" (exit 1) · Xs'
    assert "unreachable" not in result.output


def test_run_writes_a_transcript_to_output_path(runner, transcript_runbook, started_in):
    """With output_path set, run appends the run to that file and says where it went.

    The path is relative to where rundot was started, so nothing is written next to the runbook.
    """
    result = runner.invoke(cli.cli, ["run", str(transcript_runbook)], input="y\ny\n")

    transcript = started_in / "logs" / "release-1.2.0.md"
    assert result.exit_code == 0
    assert result.output.endswith("transcript: logs/release-1.2.0.md\n")
    assert sorted(path.name for path in transcript_runbook.parent.iterdir()) == ["transcript-example.md"]
    text = re.sub(r"\(\d+\.\ds\)", "(Xs)", transcript.read_text())
    text = re.sub(r"@ \S+", "@ TIME", text, count=1)
    assert text == textwrap.dedent(
        """\
        --- rundot transcript-example.md @ TIME
        --- inputs: VERSION=1.2.0 PUBLISH_TOKEN=****

        === Build ===
            echo "Building 1.2.0"
        Building 1.2.0
        exit 0 (Xs)

        === Release on GitHub ===
        confirm: Create a GitHub release for tag 1.2.0 and publish it. -> yes

        === Publish ===
            echo "Publishing 1.2.0 with $PUBLISH_TOKEN"
        Publishing 1.2.0 with ****
        exit 0 (Xs)

        --- finished: ok (Xs)
        """
    )


def test_run_shows_a_transcript_under_where_it_was_started_relative_to_there(runner, tmp_path, started_in):
    """A transcript under the directory rundot was started in is shown as a relative path, as the docs show it."""
    path = write_runbook(tmp_path, "---\ntitle: T\noutput_path: logs/run.md\n---\n\n## Only\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 0
    assert result.output.endswith(f"transcript: {Path('logs') / 'run.md'}\n")
    assert (started_in / "logs" / "run.md").exists()


def test_run_shows_a_transcript_outside_where_it_was_started_in_full(runner, tmp_path):
    """A transcript anywhere else, such as an absolute output_path, is shown as its absolute path."""
    target = tmp_path / "records" / "run.md"
    path = write_runbook(tmp_path, f"---\ntitle: T\noutput_path: {target}\n---\n\n## Only\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 0
    assert result.output.endswith(f"transcript: {target}\n")


def test_run_appends_a_second_run_to_the_transcript(runner, transcript_runbook, started_in):
    """Running twice keeps both runs, so a failed attempt and its rerun are both in the file."""
    runner.invoke(cli.cli, ["run", str(transcript_runbook)], input="y\nn\n")
    # The first run stopped part way, so the second is asked whether to resume it, and starts over.
    runner.invoke(cli.cli, ["run", str(transcript_runbook)], input="s\ny\ny\n")

    text = (started_in / "logs" / "release-1.2.0.md").read_text()
    assert text.count("--- rundot transcript-example.md @") == 2
    assert '--- finished: aborted at "Release on GitHub"\n\n--- rundot' in text
    assert re.search(r"--- finished: ok \(\d+\.\ds\)\n$", text)


def test_run_never_writes_a_secret_to_the_transcript(runner, transcript_runbook, started_in):
    """The secret is set and printed by a block, but the file only ever has ****."""
    runner.invoke(cli.cli, ["run", str(transcript_runbook)], input="y\ny\n")

    assert "s3cret" not in (started_in / "logs" / "release-1.2.0.md").read_text()


def test_run_dry_writes_no_transcript(runner, transcript_runbook, started_in):
    """--dry runs nothing, so there's nothing to record, and no file or directory is made."""
    result = runner.invoke(cli.cli, ["run", "--dry", str(transcript_runbook)])

    assert result.exit_code == 0
    assert not (started_in / "logs").exists()
    assert "transcript:" not in result.output


def test_run_writes_no_transcript_when_the_run_is_not_started(runner, transcript_runbook, started_in):
    """Declining to start writes nothing and doesn't mention a transcript."""
    result = runner.invoke(cli.cli, ["run", str(transcript_runbook)], input="n\n")

    assert result.exit_code == 1
    assert not (started_in / "logs").exists()
    assert "transcript:" not in result.output


def test_run_without_output_path_writes_no_transcript(runner, tmp_path):
    """A runbook with no output_path never mentions a transcript."""
    path = write_runbook(tmp_path, "## Only\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 0
    assert "transcript:" not in result.output
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["runbook.md"]


def test_run_reports_a_transcript_it_cannot_write_before_any_block_runs(runner, tmp_path, started_in):
    """If the transcript can't be opened, run stops with an error before the first block runs."""
    (started_in / "logs").write_text("a file where the transcript's directory should be")
    path = write_runbook(
        tmp_path, "---\ntitle: T\noutput_path: logs/run.md\n---\n\n## Only\n\n```sh run\ntouch ran\n```\n"
    )

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 1
    [error] = [line for line in result.output.splitlines() if line.startswith("Error:")]
    # The reason after the colon is the operating system's, so only the start is checked.
    assert error.startswith(f"Error: can't write the transcript to {started_in / 'logs' / 'run.md'}: ")
    assert not (started_in / "ran").exists()


def test_inputs_lists_each_input_with_its_description_pattern_and_secret_flag(runner):
    """inputs shows every declared input, lined up, with its pattern and whether it's secret."""
    result = runner.invoke(cli.cli, ["inputs", str(RUNBOOKS / "transcript-example.md")])

    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        """\
        VERSION        The version being released, e.g. 1.2.0
                       pattern: ^\\d+\\.\\d+\\.\\d+$
        PUBLISH_TOKEN  Token for the package index
                       secret
        """
    )


def test_inputs_shows_each_inputs_default(runner):
    """An input's default is listed with its other details."""
    result = runner.invoke(cli.cli, ["inputs", str(RUNBOOKS / "default-example.md")])

    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        """\
        BRANCH   The branch to release from
                 default: main
        VERSION  The version being released, e.g. 1.2.0
                 pattern: ^\\d+\\.\\d+\\.\\d+$
        """
    )


def test_inputs_shows_each_inputs_choices(runner):
    """An input's choices are listed with its other details."""
    result = runner.invoke(cli.cli, ["inputs", str(RUNBOOKS / "choices-example.md")])

    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        """\
        FE_SET  Which frontend set to rebuild
                default: comms
                choices: comms, billing, all
        """
    )


def test_inputs_reads_only_the_frontmatter(runner):
    """inputs works on a runbook whose body can't even be read, since it never reads past the frontmatter."""
    path = RUNBOOKS / "broken-body.md"
    assert runner.invoke(cli.cli, ["check", str(path)]).exit_code == 1

    result = runner.invoke(cli.cli, ["inputs", str(path)])

    assert result.exit_code == 0
    assert result.output.splitlines()[0].startswith("VERSION ")
    assert "PUBLISH_TOKEN" in result.output


def test_inputs_says_when_a_runbook_has_none(runner):
    """A runbook without inputs says so rather than printing nothing."""
    result = runner.invoke(cli.cli, ["inputs", str(RUNBOOKS / "minimal.md")])

    assert result.exit_code == 0
    assert result.output == "no inputs\n"


def test_inputs_skips_entries_that_are_not_valid_inputs(runner, tmp_path):
    """Entries missing a name or description aren't listed; check is what reports them."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        inputs:
          - name: GOOD
            description: Kept
          - name: NO_DESCRIPTION
          - just a string
        ---
        """,
    )

    result = runner.invoke(cli.cli, ["inputs", str(path)])

    assert result.exit_code == 0
    assert result.output == "GOOD  Kept\n"


def test_inputs_prints_descriptions_verbatim(runner, tmp_path):
    """Text that looks like rich markup is printed exactly as written."""
    path = write_runbook(
        tmp_path, "---\ntitle: T\ninputs:\n  - name: TAG\n    description: '[bold]tag[/bold] :smile:'\n---\n"
    )

    result = runner.invoke(cli.cli, ["inputs", str(path)])

    assert result.output == "TAG  [bold]tag[/bold] :smile:\n"


def test_inputs_reports_frontmatter_it_cannot_read(runner, tmp_path):
    """Broken frontmatter is a clean error, like check gives."""
    path = write_runbook(tmp_path, "---\ntitle: Unclosed\n\n## Step\n")

    result = runner.invoke(cli.cli, ["inputs", str(path)])

    assert result.exit_code == 1
    assert result.output == "Error: frontmatter has no closing ---\n"


def test_help_lists_inputs_command(runner):
    """--help lists the inputs command."""
    result = runner.invoke(cli.cli, ["--help"])

    assert "\n  inputs " in result.output


def test_library_lists_each_book_with_its_title_and_description(runner, monkeypatch):
    """library says where the library is, then each book's name and title, with its description underneath."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["library"])

    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        f"""\
        library: {LIBRARY}
        say-where            Say where
                             Show where a book from the library runs, and where it's kept.
        update-project-deps  Update a project's dependencies
                             Upgrade every dependency in the project you're in, then run its tests.
        """
    )


def test_library_lists_books_without_a_title_or_that_cannot_be_read(runner, tmp_path, monkeypatch):
    """A book with no title shows its name alone, and one that can't be read is listed with why, not left out."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "deploy.md").write_text("---\ntitle: Deploy\n---\n")
    (tmp_path / "notes.md").write_text("# Notes\n")
    (tmp_path / "unclosed.md").write_text("---\ntitle: Unclosed\n\n## Step\n")

    result = runner.invoke(cli.cli, ["library"])

    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        f"""\
        library: {tmp_path}
        deploy    Deploy
        notes
        unclosed  can't read it: frontmatter has no closing ---
        """
    )


def test_library_lists_only_markdown_files_directly_in_the_library(runner, tmp_path, monkeypatch):
    """Transcripts in a logs/ folder, and other files, aren't books."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "deploy.md").write_text("---\ntitle: Deploy\n---\n")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "deploy-1.2.0.md").write_text("--- rundot deploy.md @ 2026-10-13T10:00:00+01:00\n")
    (tmp_path / "deploy.sh").write_text("echo hi\n")

    result = runner.invoke(cli.cli, ["library"])

    assert result.output == f"library: {tmp_path}\ndeploy  Deploy\n"


@pytest.mark.parametrize("exists", [True, False], ids=["empty", "missing"])
def test_library_says_when_there_are_no_books(exists, runner, tmp_path, monkeypatch):
    """An empty or missing library isn't an error. It says where rundot looked, and how to look somewhere else."""
    where = tmp_path / "runbooks"
    if exists:
        where.mkdir()
    monkeypatch.setenv("RUNDOT_LIBRARY", str(where))

    result = runner.invoke(cli.cli, ["library"])

    assert result.exit_code == 0
    assert result.output == (
        f"no books in the library at {where}\nAdd runbooks there, or set RUNDOT_LIBRARY to where yours are.\n"
    )


def test_library_prints_titles_and_descriptions_verbatim(runner, tmp_path, monkeypatch):
    """A title or description is shown as written, even if it looks like rich markup."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "odd.md").write_text("---\ntitle: '[bold]Odd[/bold] :rocket:'\ndescription: '[red]x[/red]'\n---\n")

    result = runner.invoke(cli.cli, ["library"])

    assert result.output == f"library: {tmp_path}\nodd  [bold]Odd[/bold] :rocket:\n     [red]x[/red]\n"


def test_library_marks_a_book_whose_name_is_a_command(runner, tmp_path, monkeypatch):
    """rundot check is the check command, so a book called check.md says how to run it instead."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "check.md").write_text("---\ntitle: Check the deploy\n---\n")
    (tmp_path / "deploy.md").write_text("---\ntitle: Deploy\n---\n")

    result = runner.invoke(cli.cli, ["library"])

    assert result.output == textwrap.dedent(
        f"""\
        library: {tmp_path}
        check   Check the deploy
                run it with rundot run check, since rundot check is a command
        deploy  Deploy
        """
    )


# The ANSI codes rich uses, so a colour test can say what it expects by name.
STYLES = {"bold cyan": "1;36", "bold": "1", "dim": "2", "red": "31", "yellow": "33"}


def styled(output: str, style: str) -> list[str]:
    """Every piece of output written in style, in order. Colour tests use this rather than raw escape codes."""
    return re.findall(rf"\x1b\[{STYLES[style]}m(.*?)\x1b\[0m", output)


@pytest.fixture
def in_colour(monkeypatch):
    """Make rich colour its output, as it would in a terminal. The runner fixture turns colour off by default."""
    monkeypatch.setenv("FORCE_COLOR", "1")


def test_library_colours_names_so_they_stand_out(runner, in_colour, tmp_path, monkeypatch):
    """Each book's name, the thing you type, is bold cyan; descriptions and the library path are dim."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "deploy.md").write_text("---\ntitle: Deploy\ndescription: Ship it.\n---\n")
    (tmp_path / "unclosed.md").write_text("---\ntitle: Unclosed\n\n## Step\n")
    (tmp_path / "check.md").write_text("---\ntitle: Check the deploy\n---\n")

    result = runner.invoke(cli.cli, ["library"])

    assert styled(result.output, "bold cyan") == ["check", "deploy", "unclosed"]
    assert styled(result.output, "dim") == [f"library: {tmp_path}", "Ship it."]
    assert styled(result.output, "red") == ["can't read it: frontmatter has no closing ---"]
    assert styled(result.output, "yellow") == ["run it with rundot run check, since rundot check is a command"]


def test_library_never_reads_a_title_as_markup_in_colour(runner, in_colour, tmp_path, monkeypatch):
    """Colouring a line mustn't make rich read a title like [bold]Odd[/bold] as markup."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "odd.md").write_text("---\ntitle: '[bold]Odd[/bold] :rocket:'\n---\n")

    result = runner.invoke(cli.cli, ["library"])

    assert "[bold]Odd[/bold] :rocket:" in result.output


def test_the_picker_colours_numbers_names_and_the_question(runner, in_colour, monkeypatch):
    """The numbers are dim, the names bold cyan, and the question bold, with how to quit dim after it.

    color=True, since Click takes the colour out of a prompt that isn't going to a terminal.
    """
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["run"], input="\n", color=True)

    assert styled(result.output, "bold cyan") == ["say-where", "update-project-deps"]
    assert styled(result.output, "dim") == ["  1.", "  2.", "(q to quit)"]
    assert "\x1b[1mRun which?\x1b[0m" in result.output


def test_inputs_colours_names_and_dims_their_details(runner, in_colour):
    """Each input's name is bold cyan, its details dim, and secret yellow, so a secret stands out."""
    result = runner.invoke(cli.cli, ["inputs", str(RUNBOOKS / "transcript-example.md")])

    assert styled(result.output, "bold cyan") == ["VERSION", "PUBLISH_TOKEN"]
    assert styled(result.output, "dim") == ["pattern: ^\\d+\\.\\d+\\.\\d+$"]
    assert styled(result.output, "yellow") == ["secret"]


def test_an_inputs_prompt_dims_its_default_and_choices(runner, in_colour, monkeypatch):
    """The default and choices in a prompt are dim, so the question itself is easy to read.

    color=True, since Click takes the colour out of a prompt that isn't going to a terminal.
    """
    monkeypatch.delenv("FE_SET", raising=False)

    result = runner.invoke(cli.cli, ["run", str(RUNBOOKS / "choices-example.md")], input="\ny\n", color=True)

    assert result.exit_code == 0, result.output
    assert styled(result.output, "dim")[:2] == ["[comms]", "(comms, billing, all)"]


def test_menus_have_no_colour_outside_a_terminal(runner, monkeypatch):
    """With no terminal, as when piped, nothing is coloured, so output stays easy to read and to grep."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    for arguments in (["library"], ["inputs", str(RUNBOOKS / "transcript-example.md")]):
        assert "\x1b[" not in runner.invoke(cli.cli, arguments).output
    assert "\x1b[" not in runner.invoke(cli.cli, ["run"], input="\n").output


def test_help_lists_library_command(runner):
    """--help lists the library command."""
    result = runner.invoke(cli.cli, ["--help"])

    assert "\n  library " in result.output


def test_run_with_no_runbook_picks_a_book_from_the_library_and_runs_it(runner, monkeypatch, started_in):
    """rundot run lists the library's books by number, and runs the one picked, where rundot was started."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["run"], input="1\ny\n")

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[:3] == [
        "  1. say-where            Say where",
        "  2. update-project-deps  Update a project's dependencies",
        "Run which? (q to quit) 1",
    ]
    assert lines[3].startswith("╭─ Say where ")
    assert str(started_in.resolve()) in printed(result.output)
    assert finished(result.output).startswith("✓ finished ok")


@pytest.mark.parametrize("arguments", [["run", "--dry"], ["--dry"]], ids=["run --dry", "--dry alone"])
def test_the_picker_works_under_dry(arguments, runner, monkeypatch):
    """--dry applies to the book picked, with or without run."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))
    monkeypatch.setenv("BRANCH", "update-deps")

    result = runner.invoke(cli.cli, arguments, input="2\n")

    assert result.exit_code == 0, result.output
    assert "Run which? (q to quit) 2" in result.output.splitlines()
    assert 'echo "git switch -c update-deps"' in printed(result.output)
    assert finished(result.output) == "dry run, nothing was run"


def test_the_picker_works_under_step(runner, monkeypatch):
    """--step applies to the book picked: it asks before each run block."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["run", "--step"], input="1\ny\ns\n")

    assert result.exit_code == 0, result.output
    assert "  ├ Run this block? [y]es / [s]kip / [q]uit s" in result.output.splitlines()
    assert "  └ ↷ skipped" in result.output.splitlines()


@pytest.mark.parametrize("answer", ["0", "3", "two", "say-where", "-1"])
def test_the_picker_asks_again_after_an_answer_that_is_not_a_listed_number(answer, runner, monkeypatch):
    """Only a number from the list picks a book; anything else, even a book's name, gets the question again."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["run", "--dry"], input=f"{answer}\n1\n")

    assert result.exit_code == 0, result.output
    assert result.output.count("Run which?") == 2
    assert result.output.splitlines()[2:5] == [
        f"Run which? (q to quit) {answer}",
        "Pick a number from 1 to 2, or q to quit.",
        "Run which? (q to quit) 1",
    ]
    assert title(result.output) == "Say where"


@pytest.mark.parametrize("answer", ["", "q"], ids=["blank", "q"])
def test_q_or_a_blank_answer_to_the_picker_runs_nothing(answer, runner, monkeypatch, tmp_path, started_in):
    """q, or pressing enter, at the picker ends without running anything or writing a transcript, and exits 1."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "record.md").write_text(
        "---\ntitle: Record\noutput_path: logs/run.md\n---\n\n## S\n\n```sh run\ntouch ran\n```\n"
    )

    result = runner.invoke(cli.cli, ["run"], input=f"{answer}\n")

    assert result.exit_code == 1
    assert result.output == f"  1. record  Record\nRun which? (q to quit) {answer}\n"
    assert sorted(path.name for path in started_in.iterdir()) == []


def test_q_at_the_picker_quits_even_with_a_book_called_q(runner, monkeypatch, tmp_path, started_in):
    """Books are picked by number, so q always quits, even when there's a q.md in the library."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "q.md").write_text("---\ntitle: Q\n---\n\n## S\n\n```sh run\ntouch ran\n```\n")

    result = runner.invoke(cli.cli, ["run"], input="q\n")

    assert result.exit_code == 1
    assert sorted(path.name for path in started_in.iterdir()) == []


def test_ctrl_c_at_the_picker_runs_nothing(runner, monkeypatch, started_in):
    """Ctrl-C at the picker ends as quietly as a blank answer, without a traceback."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    def ctrl_c(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(click.termui, "visible_prompt_func", ctrl_c)

    result = runner.invoke(cli.cli, ["run"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert sorted(path.name for path in started_in.iterdir()) == []


def test_the_picker_with_an_empty_library_is_an_error(runner, empty_library):
    """There's nothing to pick, so rundot run says where it looked, and exits 1."""
    result = runner.invoke(cli.cli, ["run"])

    assert result.exit_code == 1
    assert result.output == (
        f"Error: no books in the library at {empty_library} to pick from. "
        "Give a runbook to run, or set RUNDOT_LIBRARY to where yours are.\n"
    )


def test_the_picker_lists_a_book_that_cannot_be_read_and_reports_it_if_picked(runner, monkeypatch, tmp_path):
    """A book with broken frontmatter is listed with why, like in rundot library, and picking it is a clean error."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(tmp_path))
    (tmp_path / "unclosed.md").write_text("---\ntitle: Unclosed\n\n## Step\n")

    result = runner.invoke(cli.cli, ["run"], input="1\n")

    assert result.exit_code == 1
    assert result.output == (
        "  1. unclosed  can't read it: frontmatter has no closing ---\n"
        "Run which? (q to quit) 1\n"
        "Error: frontmatter has no closing ---\n"
    )


def test_check_and_inputs_still_need_a_runbook(runner, monkeypatch):
    """Only run has a picker."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    for command in ("check", "inputs"):
        result = runner.invoke(cli.cli, [command])

        assert result.exit_code == 2
        assert "Missing argument 'RUNBOOK'" in result.output


class EchoBackend:
    """An external backend, defined here as if it shipped in another package.

    It prints each line of a fakelang block back as "echo: <line>", and fails with exit 7 at a line that
    says FAIL. Validation flags a line that says BAD.
    """

    name = "echo"
    languages = ("fakelang",)

    def validate(self, code):
        return [
            Problem("BAD isn't allowed", line=n) for n, line in enumerate(code.splitlines(), start=1) if line == "BAD"
        ]

    def run(self, code, *, frontmatter, env, cwd, output):
        for line in code.splitlines():
            if line == "FAIL":
                return 7
            output(f"echo: {line}")
        return 0


@pytest.fixture
def external_backend(monkeypatch):
    """Install EchoBackend alongside rundot's own backends, the way another package registering it would."""
    installed = list(backends.installed_entry_points())
    echo = EntryPoint(name="echo", value=f"{__name__}:EchoBackend", group=backends.ENTRY_POINT_GROUP)
    monkeypatch.setattr(backends, "installed_entry_points", lambda: [*installed, echo])


def test_backends_lists_each_backend_with_its_languages_and_where_it_came_from(runner):
    """backends shows rundot's own backends, the languages each runs, and the package that registered it."""
    version = importlib.metadata.version("rundot")

    result = runner.invoke(cli.cli, ["backends"])

    assert result.exit_code == 0
    assert result.output == (
        f"python  python, py       rundot.backends.python:PythonBackend (rundot {version})\n"
        f"shell   sh, bash, shell  rundot.backends.shell:ShellBackend (rundot {version})\n"
    )


def test_backends_lists_an_external_backend(runner, external_backend):
    """A backend registered by another package is listed with the built-in ones."""
    result = runner.invoke(cli.cli, ["backends"])

    assert result.exit_code == 0
    [echo] = [line for line in result.output.splitlines() if line.startswith("echo ")]
    assert echo.split() == ["echo", "fakelang", f"{__name__}:EchoBackend"]


def test_run_runs_an_external_backends_blocks(runner, external_backend, tmp_path):
    """run runs a block in an external backend's language end to end, alongside built-in blocks."""
    path = write_runbook(
        tmp_path,
        """\
        ## Mixed

        ```sh run
        echo "from shell"
        ```

        ```fakelang run
        hello
        world
        ```
        """,
    )

    result = runner.invoke(cli.cli, ["run", "--show-code", str(path)], input="y\n")

    assert result.exit_code == 0
    assert "from shell" in printed(result.output)
    assert "\n  ┌ fakelang · 10:02:13.482\n  │ hello\n  │ world\n  ├ output\n  │ echo: hello\n  │ echo: world\n" in (
        result.output
    )


def test_run_stops_at_an_external_block_that_fails(runner, external_backend, tmp_path):
    """An external backend's exit code fails the run like any other block's."""
    path = write_runbook(tmp_path, "## Fails\n\n```fakelang run\nbefore\nFAIL\nafter\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 1
    assert "echo: before" in printed(result.output)
    assert "echo: after" not in result.output
    assert finished(normalized(result.output)) == '✗ failed at "Fails" (exit 7) · Xs'


def test_check_uses_an_external_backends_validation(runner, external_backend, tmp_path):
    """check reports an external backend's problems on the right runbook line."""
    path = write_runbook(tmp_path, "## Step\n\n```fakelang run\nfine\nBAD\n```\n")

    result = runner.invoke(cli.cli, ["check", str(path)])

    assert result.exit_code == 1
    assert f"{path}:9: error: BAD isn't allowed\n" in result.output


def test_backends_reports_backends_that_cannot_load(runner, monkeypatch):
    """Two backends claiming one language is a clean error here too, not a crash."""

    def conflicting():
        raise BackendError("language 'sh' is claimed by both 'shell' and 'rival'")

    monkeypatch.setattr(cli, "load_backend_sources", conflicting)

    result = runner.invoke(cli.cli, ["backends"])

    assert result.exit_code == 1
    assert result.output == "Error: language 'sh' is claimed by both 'shell' and 'rival'\n"


def test_help_lists_backends_command(runner):
    """--help lists the backends command."""
    result = runner.invoke(cli.cli, ["--help"])

    assert "\n  backends " in result.output


def test_run_step_records_skipped_blocks_in_the_transcript(runner, transcript_runbook, started_in):
    """A block skipped under --step is in the transcript as skipped, and the run still finishes ok."""
    result = runner.invoke(cli.cli, ["run", "--step", str(transcript_runbook)], input="y\ny\ny\ns\n")

    assert result.exit_code == 0
    text = (started_in / "logs" / "release-1.2.0.md").read_text()
    assert '=== Publish ===\n    echo "Publishing 1.2.0 with $PUBLISH_TOKEN"\nskipped\n' in text
    assert "Building 1.2.0\n" in text
    assert re.search(r"--- finished: ok \(\d+\.\ds\)\n$", text)


def test_run_refuses_a_runbook_that_declares_an_input_twice(runner):
    """run won't start a runbook with a repeated input name, since it can't tell which declaration is meant."""
    path = RUNBOOKS / "broken" / "duplicate-input-name.md"

    result = runner.invoke(cli.cli, ["run", str(path)], input="1.2.0\ny\n")

    assert result.exit_code == 1
    assert result.output == f"{path}:6: error: input VERSION is declared twice (first on line 4)\n\n1 error\n"


@pytest.mark.parametrize(
    "ask", [lambda prompter: prompter.confirm("Start? [y/N]"), lambda prompter: prompter.ask(cli.Input("V", "v"), None)]
)
def test_click_prompter_turns_ctrl_c_back_into_keyboard_interrupt(monkeypatch, ask):
    """Click turns Ctrl-C at a prompt into Abort. The prompter turns it back, so the runner can finish the run."""

    def ctrl_c(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(click.termui, "visible_prompt_func", ctrl_c)

    with pytest.raises(KeyboardInterrupt):
        ask(cli.ClickPrompter(cli.Console()))


def test_click_prompter_leaves_end_of_input_as_abort(monkeypatch):
    """Running out of input isn't Ctrl-C, so it stays Click's Abort."""

    def end_of_input(*args, **kwargs):
        raise EOFError

    monkeypatch.setattr(click.termui, "visible_prompt_func", end_of_input)

    with pytest.raises(click.Abort):
        cli.ClickPrompter(cli.Console()).confirm("Start? [y/N]")


def test_run_asks_for_input_blocks_as_the_run_reaches_them(runner, input_block_runbook):
    """Each input block's prompt comes where the block is, after the steps before it have run."""
    result = runner.invoke(cli.cli, ["run", str(input_block_runbook)], input="y\ny\n42\n123456\n")

    assert result.exit_code == 0
    shown = normalized(result.output)
    assert shown[shown.index("1/2  Open the pull request") : shown.index("╭─╮")] == textwrap.dedent(
        """\
        1/2  Open the pull request ━
        ╭─ confirm ─╮
        │ Open a pull request for 1.2.0 on GitHub. │
        ╰─╯
        Continue? [y/N] y
        PR (The number GitHub gave the pull request): 42

          ┌ sh · 10:02:13.482
          │ Merging pull request 42 for 1.2.0
          └ ✓ exit 0 · Xs

        2/2  Publish ━
        OTP (The code from your authenticator app): \n
          ┌ sh · 10:02:13.482
          │ Publishing 1.2.0 with code ****
          └ ✓ exit 0 · Xs

        """
    )
    assert "123456" not in result.output


def test_run_records_input_blocks_in_the_transcript(runner, input_block_runbook, started_in):
    """The transcript shows where each input block was answered, with the secret as ****."""
    runner.invoke(cli.cli, ["run", str(input_block_runbook)], input="y\ny\n42\n123456\n")

    text = (started_in / "logs" / "pr-release.md").read_text()
    assert "confirm: Open a pull request for 1.2.0 on GitHub. -> yes\ninput: PR=42\n" in text
    assert "=== Publish ===\ninput: OTP=****\n" in text
    assert "123456" not in text


def test_run_dry_shows_input_blocks_without_asking(runner, input_block_runbook, started_in):
    """--dry says where the run would stop to ask, and leaves those placeholders as written."""
    result = runner.invoke(cli.cli, ["run", "--dry", str(input_block_runbook)])

    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert "  input: PR (The number GitHub gave the pull request), asked here" in lines
    assert "  input: OTP (The code from your authenticator app), asked here" in lines
    assert 'echo "Merging pull request <PR> for 1.2.0"' in printed(result.output)
    assert not (started_in / "logs").exists()


def test_inputs_lists_input_blocks_with_the_step_that_asks_for_them(runner):
    """Block inputs come after the frontmatter ones, each with its pattern, secret flag and step."""
    result = runner.invoke(cli.cli, ["inputs", str(RUNBOOKS / "input-block-example.md")])

    assert result.exit_code == 0
    assert result.output == textwrap.dedent(
        """\
        VERSION  The version being released, e.g. 1.2.0
                 pattern: ^\\d+\\.\\d+\\.\\d+$
        PR       The number GitHub gave the pull request
                 pattern: ^\\d+$
                 asked in "Open the pull request"
        OTP      The code from your authenticator app
                 pattern: ^\\d{6}$
                 secret
                 asked in "Publish"
        """
    )


def test_inputs_still_lists_frontmatter_inputs_when_the_body_cannot_be_read(runner):
    """Block inputs need the body, but a body that can't be read doesn't stop the frontmatter ones being listed."""
    result = runner.invoke(cli.cli, ["inputs", str(RUNBOOKS / "broken-body.md")])

    assert result.exit_code == 0
    assert result.output.splitlines()[0].startswith("VERSION ")
    assert "asked in" not in result.output


def test_a_blocks_time_is_local_to_the_millisecond():
    """A bracket shows the time its block started, to the millisecond, with leading zeros kept."""
    assert cli.block_time(datetime(2026, 11, 4, 9, 5, 7, 4999, tzinfo=timezone.utc)) == "09:05:07.004"


# --- Resuming a run ---


@pytest.fixture
def resume_runbook(tmp_path, monkeypatch):
    """A copy of the resume example, whose Publish step fails until there's a file called fixed where rundot runs.

    VERSION is set in the environment for the first run; PUBLISH_TOKEN is asked for.
    """
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.delenv("PUBLISH_TOKEN", raising=False)
    return Path(shutil.copy(RUNBOOKS / "resume-example.md", tmp_path))


def saved_state(runbook: Path, cwd: Path) -> state_module.RunState | None:
    return state_module.RunState.load(state_module.state_path(os.environ, runbook, cwd), warn=pytest.fail)


def fail_once(runner, runbook: Path) -> None:
    """Run the resume example until it fails at Publish, leaving its state behind."""
    result = runner.invoke(cli.cli, ["run", str(runbook)], input="s3cret\ny\n")
    assert result.exit_code == 1, result.output
    assert finished(normalized(result.output)) == '✗ failed at "Publish" (exit 1) · Xs'


def test_a_failed_run_resumes_at_the_step_it_stopped_in(runner, resume_runbook, started_in, monkeypatch):
    """Once it's fixed, answering r runs only the step that failed and those after it, and asks for secrets again."""
    fail_once(runner, resume_runbook)
    (started_in / "fixed").touch()
    monkeypatch.delenv("VERSION")  # saved from the first run

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="r\nagain\ny\n")

    assert result.exit_code == 0, result.output
    assert re.search(
        r"^Last run stopped at 3/4 Publish: failed \(exit 1\), \d{4}-\d\d-\d\d \d\d:\d\d\.$", result.output, re.M
    )
    assert "[r]esume / [s]tart over / [q]uit:" in result.output
    assert "PUBLISH_TOKEN (Token for the package index)" in result.output
    assert printed(result.output) == ["Publishing 1.2.0 with ****", "Announced 1.2.0"]
    assert "1/4  Build" not in result.output
    assert "3/4  Publish" in result.output
    assert saved_state(resume_runbook, started_in) is None  # finished ok


def test_a_resumed_run_shows_where_it_resumes_and_the_steps_already_done(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    (started_in / "fixed").touch()

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="r\nagain\ny\n")

    rows = overview(result.output)
    assert rows["resuming"] == ["3/4 Publish"]
    assert [row.split() for row in rows["steps"]] == [
        ["1.", "Build", "done"],
        ["2.", "Test", "done"],
        ["3.", "Publish"],
        ["4.", "Announce"],
    ]
    assert rows["blocks"] == ["2 run blocks"]


def test_the_question_asks_again_until_the_answer_is_r_s_or_q(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="x\n\nq\n")

    assert result.exit_code == 1
    assert result.output.count("[r]esume / [s]tart over / [q]uit:") == 3


def test_quitting_at_the_question_runs_nothing_and_keeps_the_state(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    before = saved_state(resume_runbook, started_in)

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="q\n")

    assert result.exit_code == 1
    assert "Start?" not in result.output
    assert saved_state(resume_runbook, started_in) == before


def test_ctrl_c_at_the_question_runs_nothing_and_keeps_the_state(runner, resume_runbook, started_in, monkeypatch):
    fail_once(runner, resume_runbook)
    before = saved_state(resume_runbook, started_in)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_prompt", interrupted)
    result = runner.invoke(cli.cli, ["run", str(resume_runbook)])

    assert result.exit_code == 1
    assert saved_state(resume_runbook, started_in) == before


def test_starting_over_at_the_question_deletes_the_state_and_runs_from_the_first_step(
    runner, resume_runbook, started_in
):
    """s deletes the state straight away, so it's gone even if the new run is then declined at Start?."""
    fail_once(runner, resume_runbook)

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="s\nagain\nn\n")

    assert result.exit_code == 1
    assert "resuming" not in overview(result.output)
    assert saved_state(resume_runbook, started_in) is None


def test_starting_over_runs_from_the_first_step(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    (started_in / "fixed").touch()

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="s\nagain\ny\n")

    assert result.exit_code == 0
    assert printed(result.output)[0] == "Building 1.2.0"


def test_restart_deletes_the_state_without_asking(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)

    result = runner.invoke(cli.cli, ["run", str(resume_runbook), "--restart"], input="again\nn\n")

    assert result.exit_code == 1
    assert "Last run stopped" not in result.output
    assert "[r]esume" not in result.output
    assert saved_state(resume_runbook, started_in) is None


def test_resume_resumes_without_asking(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    (started_in / "fixed").touch()

    result = runner.invoke(cli.cli, ["run", str(resume_runbook), "--resume"], input="again\ny\n")

    assert result.exit_code == 0, result.output
    assert "Last run stopped at 3/4 Publish" in result.output
    assert "[r]esume" not in result.output
    assert printed(result.output) == ["Publishing 1.2.0 with ****", "Announced 1.2.0"]


def test_resume_with_nothing_to_resume_is_an_error(runner, resume_runbook, started_in):
    result = runner.invoke(cli.cli, ["run", str(resume_runbook), "--resume"])

    assert result.exit_code == 1
    assert f"nothing to resume for {resume_runbook.name} in {started_in}" in result.output


@pytest.mark.parametrize(
    "flags", [["--resume", "--restart"], ["--dry", "--resume"], ["--dry", "--restart"]], ids=" ".join
)
def test_contradicting_flags_are_a_usage_error(runner, resume_runbook, flags):
    result = runner.invoke(cli.cli, ["run", str(resume_runbook), *flags])

    assert result.exit_code == 2
    assert "can't be used together" in result.output


def test_a_dry_run_never_reads_or_writes_state(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    before = saved_state(resume_runbook, started_in)

    result = runner.invoke(cli.cli, ["run", str(resume_runbook), "--dry"])

    assert result.exit_code == 0
    assert "Last run stopped" not in result.output
    assert saved_state(resume_runbook, started_in) == before


def test_a_dry_run_writes_no_state(runner, resume_runbook, started_in):
    runner.invoke(cli.cli, ["run", str(resume_runbook), "--dry"])

    assert not state_module.state_dir(os.environ).exists()
    assert saved_state(resume_runbook, started_in) is None


def test_a_run_that_finishes_ok_leaves_no_state(runner, resume_runbook, started_in):
    (started_in / "fixed").touch()

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="s3cret\ny\n")

    assert result.exit_code == 0
    assert saved_state(resume_runbook, started_in) is None


def test_the_same_runbook_in_another_directory_has_its_own_state(runner, resume_runbook, started_in, monkeypatch):
    fail_once(runner, resume_runbook)
    elsewhere = started_in / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="s3cret\nn\n")

    assert "Last run stopped" not in result.output


def edit_step(runbook: Path, old: str, new: str) -> None:
    runbook.write_text(runbook.read_text().replace(old, new, 1))


def test_a_changed_skipped_step_warns_before_resuming(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    edit_step(resume_runbook, 'echo "Testing <VERSION>"', 'echo "Testing <VERSION> again"')

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="q\n")

    assert f'{resume_runbook.name} has changed since that run: "Test" is different.' in result.output


def test_several_changed_steps_are_all_named(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    edit_step(resume_runbook, 'echo "Building <VERSION>"', 'echo "Building <VERSION> again"')
    edit_step(resume_runbook, 'echo "Testing <VERSION>"', 'echo "Testing <VERSION> again"')

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="q\n")

    assert 'has changed since that run: "Build" and "Test" are different.' in result.output


def test_a_renamed_resume_step_warns_before_resuming(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    edit_step(resume_runbook, "## Publish", "## Publish to the index")

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="q\n")

    assert 'has changed since that run: step 3 was "Publish" and is now "Publish to the index".' in result.output


def test_a_changed_resume_step_or_later_step_does_not_warn(runner, resume_runbook, started_in):
    """Those steps run again anyway, so a fix to them is expected."""
    fail_once(runner, resume_runbook)
    edit_step(resume_runbook, "test -f fixed", "test -f fixed-now")
    edit_step(resume_runbook, 'echo "Announced', 'echo "Told everyone about')

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="q\n")

    assert "has changed" not in result.output


def test_a_runbook_with_fewer_steps_starts_over(runner, resume_runbook, started_in):
    fail_once(runner, resume_runbook)
    text = resume_runbook.read_text()
    resume_runbook.write_text(text[: text.index("## Announce")])

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="s3cret\nn\n")

    assert f"{resume_runbook.name} now has fewer steps than that run, so it starts over." in result.output
    assert "[r]esume" not in result.output
    assert saved_state(resume_runbook, started_in) is None


def test_a_broken_state_file_warns_and_runs_from_the_start(runner, resume_runbook, started_in):
    path = state_module.state_path(os.environ, resume_runbook, started_in)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="s3cret\nn\n")

    assert f"ignoring the saved run at {path}: it isn't valid JSON" in result.output
    assert "[r]esume" not in result.output


def write_state(runbook: Path, cwd: Path, **changes) -> None:
    """Save a state for runbook in cwd, as a run that failed at Publish would, with changes made to it."""
    stopped = state_module.RunState(
        runbook=str(runbook.resolve()),
        directory=str(cwd.resolve()),
        started_at="2026-11-13T14:02:11+00:00",
        stopped="failed",
        step=2,
        block=0,
        steps=tuple((step.name, state_module.step_hash(step)) for step in parse(runbook).steps),
        inputs={"VERSION": "1.2.0"},
    )
    replace(stopped, **changes).save(state_module.state_path(os.environ, runbook, cwd))


@pytest.mark.parametrize(
    ("stopped", "said"),
    [
        ("aborted", "aborted"),
        ("interrupted", "interrupted"),
        ("needs_human_input", "needs human input"),
        ("running", "killed while running"),
    ],
)
def test_the_question_says_how_the_last_run_stopped(runner, resume_runbook, started_in, stopped, said):
    write_state(resume_runbook, started_in, stopped=stopped)

    result = runner.invoke(cli.cli, ["run", str(resume_runbook)], input="q\n")

    assert f"Last run stopped at 3/4 Publish: {said}, " in result.output


CONFIRM_RUNBOOK = """\
## First

```sh run
echo first
```

```confirm
Publish the notes.
```

```sh run
echo after the confirm
```
"""


def test_a_run_stopped_for_human_input_resumes_at_its_block(runner, tmp_path, started_in):
    """The confirm it stopped at counts as answered yes, and the blocks before it in its step don't run."""
    path = write_runbook(tmp_path, CONFIRM_RUNBOOK)
    write_state(path, started_in, stopped="needs_human_input", step=0, block=1, inputs={})

    result = runner.invoke(cli.cli, ["run", str(path)], input="r\ny\n")

    assert result.exit_code == 0, result.output
    assert printed(result.output) == ["after the confirm"]
    assert "Continue?" not in result.output


def test_a_run_stopped_for_human_input_in_a_changed_step_resumes_at_its_first_block(runner, tmp_path, started_in):
    """The saved block may not be the same block any more, so the whole step runs again."""
    path = write_runbook(tmp_path, CONFIRM_RUNBOOK)
    write_state(path, started_in, stopped="needs_human_input", step=0, block=1, inputs={})
    edit_step(path, "echo first", "echo first, changed")

    result = runner.invoke(cli.cli, ["run", str(path)], input="r\ny\ny\n")

    assert result.exit_code == 0, result.output
    assert printed(result.output) == ["first, changed", "after the confirm"]


def test_a_resumed_runs_transcript_says_where_it_resumed_from(runner, resume_runbook, started_in):
    text = resume_runbook.read_text().replace("---\n\n#", "output_path: run.log\n---\n\n#", 1)
    resume_runbook.write_text(text)
    fail_once(runner, resume_runbook)
    (started_in / "fixed").touch()
    stopped = saved_state(resume_runbook, started_in)
    assert stopped is not None

    runner.invoke(cli.cli, ["run", str(resume_runbook)], input="r\nagain\ny\n")

    second = (started_in / "run.log").read_text().split("\n\n--- rundot ")[1]
    lines = second.splitlines()
    assert lines[1] == f'--- resumed at "Publish", from the run at {stopped.started_at}'
    assert lines[2] == "--- inputs: VERSION=1.2.0 PUBLISH_TOKEN=****"


# --- Running with --no-input ---


@pytest.fixture
def human_runbook(tmp_path, monkeypatch):
    """A copy of the needs human input example, with VERSION set and PR not, away from where its state is."""
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.delenv("PR", raising=False)
    monkeypatch.delenv("RUNDOT_NO_INPUT", raising=False)
    return Path(shutil.copy(RUNBOOKS / "needs-human-input-example.md", tmp_path))


def no_input(runner, *arguments: str, **options):
    """Run rundot with no input at all, so any prompt reads end of input and the run can't go on."""
    return runner.invoke(cli.cli, ["run", *arguments], **options)


def test_no_input_never_asks_to_start(runner, resume_runbook, started_in, monkeypatch):
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")
    (started_in / "fixed").touch()

    result = no_input(runner, str(resume_runbook), "--no-input")

    assert result.exit_code == 0, result.output
    assert "Start?" not in result.output
    assert printed(result.output)[-1] == "Announced 1.2.0"


def test_rundot_no_input_1_acts_like_the_flag(runner, resume_runbook, started_in, monkeypatch):
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")
    monkeypatch.setenv("RUNDOT_NO_INPUT", "1")
    (started_in / "fixed").touch()

    result = no_input(runner, str(resume_runbook))

    assert result.exit_code == 0, result.output
    assert "Start?" not in result.output


@pytest.mark.parametrize("value", ["", "0", "yes", "true"])
def test_rundot_no_input_is_off_for_any_value_but_1(runner, resume_runbook, monkeypatch, value):
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")
    monkeypatch.setenv("RUNDOT_NO_INPUT", value)

    result = no_input(runner, str(resume_runbook), input="n\n")

    assert "Start? [y/N]" in result.output


def test_no_input_names_every_missing_input_and_runs_nothing(runner, resume_runbook, started_in, monkeypatch):
    monkeypatch.delenv("VERSION")

    result = no_input(runner, str(resume_runbook), "--no-input")

    assert result.exit_code == 1
    assert "missing inputs: VERSION, PUBLISH_TOKEN. Set them in the environment." in result.output
    assert "╭─" not in result.output  # no overview: nothing has started


def test_no_input_takes_a_default_for_a_missing_input(runner, tmp_path, monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Defaults
        inputs:
          - name: ENVIRONMENT
            description: Where to deploy
            default: staging
        ---

        ## Deploy

        ```sh run
        echo "deploying to <ENVIRONMENT>"
        ```
        """,
    )

    result = no_input(runner, str(path), "--no-input")

    assert result.exit_code == 0, result.output
    assert printed(result.output) == ["deploying to staging"]


def test_no_input_fails_on_a_default_that_does_not_fit_its_pattern():
    """check reports it too; a run that goes ahead anyway fails rather than asking again."""
    with pytest.raises(InputError, match="COUNT must match"):
        collect([Input("COUNT", "How many", pattern=r"\d+", default="many")], {}, cli.NoInputPrompter())


def test_no_input_prompter_needs_a_person_for_every_question_and_input_without_a_default():
    prompter = cli.NoInputPrompter()

    with pytest.raises(NeedsHumanInput):
        prompter.confirm("Continue? [y/N]")
    with pytest.raises(NeedsHumanInput):
        prompter.ask(Input("PR", "The pull request"), None)
    assert prompter.ask(Input("ENV", "Where", default="staging"), None) == ""


def test_no_input_stops_at_a_confirm_with_exit_3_and_says_what_to_do(runner, human_runbook, started_in):
    result = no_input(runner, str(human_runbook), "--no-input")

    assert result.exit_code == 3, result.output
    assert finished(normalized(result.output)) == '⏸ needs human input at "Release notes"'
    assert result.output.rstrip().splitlines()[-1] == (
        "needs human input: Publish the GitHub release notes for v1.2.0. Run again once it's done."
    )
    assert printed(result.output) == ["Building 1.2.0"]


def test_no_input_carries_on_after_the_confirm_it_stopped_at(runner, human_runbook, started_in):
    no_input(runner, str(human_runbook), "--no-input")

    result = no_input(runner, str(human_runbook), "--no-input")

    assert result.exit_code == 3, result.output
    assert "resuming at 2/3 Release notes" in result.output
    assert "Building 1.2.0" not in printed(result.output)
    assert result.output.rstrip().splitlines()[-1] == (
        "needs human input: set PR (The number GitHub gave the pull request) and run again."
    )


def test_no_input_carries_on_at_the_input_block_once_it_is_set(runner, human_runbook, started_in, monkeypatch):
    no_input(runner, str(human_runbook), "--no-input")
    no_input(runner, str(human_runbook), "--no-input")
    monkeypatch.setenv("PR", "42")

    result = no_input(runner, str(human_runbook), "--no-input")

    assert result.exit_code == 0, result.output
    assert "resuming at 3/3 Announce" in result.output
    assert printed(result.output) == ["Announcing 1.2.0 in PR 42"]
    assert saved_state(human_runbook, started_in) is None


def test_no_input_records_the_confirm_as_answered_yes_on_resume(runner, human_runbook, started_in, monkeypatch):
    text = human_runbook.read_text().replace("---\n\n#", "output_path: run.log\n---\n\n#", 1)
    human_runbook.write_text(text)
    no_input(runner, str(human_runbook), "--no-input")
    monkeypatch.setenv("PR", "42")

    no_input(runner, str(human_runbook), "--no-input")

    log = (started_in / "run.log").read_text()
    assert '--- finished: needs human input at "Release notes"' in log
    assert "confirm: Publish the GitHub release notes for v1.2.0. ... -> yes" in log


def test_no_input_resumes_a_failed_run_by_itself(runner, resume_runbook, started_in, monkeypatch):
    fail_once(runner, resume_runbook)
    (started_in / "fixed").touch()
    monkeypatch.setenv("PUBLISH_TOKEN", "again")

    result = no_input(runner, str(resume_runbook), "--no-input")

    assert result.exit_code == 0, result.output
    assert "resuming at 3/4 Publish" in result.output
    assert printed(result.output) == ["Publishing 1.2.0 with ****", "Announced 1.2.0"]


def test_no_input_with_restart_starts_over(runner, resume_runbook, started_in, monkeypatch):
    fail_once(runner, resume_runbook)
    (started_in / "fixed").touch()
    monkeypatch.setenv("PUBLISH_TOKEN", "again")

    result = no_input(runner, str(resume_runbook), "--no-input", "--restart")

    assert result.exit_code == 0, result.output
    assert "resuming" not in result.output
    assert printed(result.output)[0] == "Building 1.2.0"


def test_no_input_counts_saved_values_as_present(runner, resume_runbook, started_in, monkeypatch):
    fail_once(runner, resume_runbook)
    monkeypatch.delenv("VERSION")
    monkeypatch.setenv("PUBLISH_TOKEN", "again")

    result = no_input(runner, str(resume_runbook), "--no-input")

    assert "missing inputs" not in result.output
    assert "resuming at 3/4 Publish" in result.output


def test_no_input_names_a_secret_input_block_in_a_skipped_step(runner, tmp_path, started_in, monkeypatch):
    """Secrets aren't saved, so one asked for in a step that's done must be set again for the rest of the run."""
    monkeypatch.delenv("OTP", raising=False)
    path = write_runbook(
        tmp_path,
        """\
        ## Log in

        ```input
        name: OTP
        description: A one-time password
        secret: true
        ```

        ## Use it

        ```sh run
        echo "otp $OTP"
        ```
        """,
    )
    write_state(path, started_in, step=1, inputs={})

    result = no_input(runner, str(path), "--no-input")

    assert result.exit_code == 1
    assert "missing inputs: OTP. Set them in the environment." in result.output


def test_no_input_ignores_step_true_in_the_runbook(runner, tmp_path):
    path = write_runbook(tmp_path, "---\ntitle: T\nstep: true\n---\n\n## One\n\n```sh run\necho ran\n```\n")

    result = no_input(runner, str(path), "--no-input")

    assert result.exit_code == 0, result.output
    assert "Run this block?" not in result.output


@pytest.mark.parametrize(
    ("arguments", "environment", "message"),
    [
        (["--no-input", "--step"], {}, "--no-input and --step can't be used together"),
        (["--no-input", "--dry"], {}, "--no-input and --dry can't be used together"),
        (["--step"], {"RUNDOT_NO_INPUT": "1"}, "RUNDOT_NO_INPUT=1 and --step can't be used together"),
        (["--dry"], {"RUNDOT_NO_INPUT": "1"}, "RUNDOT_NO_INPUT=1 and --dry can't be used together"),
    ],
)
def test_no_input_contradicting_flags_are_a_usage_error(
    runner, resume_runbook, monkeypatch, arguments, environment, message
):
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    result = no_input(runner, str(resume_runbook), *arguments)

    assert result.exit_code == 2
    assert message in result.output


def test_no_input_with_no_step_is_fine(runner, resume_runbook, started_in, monkeypatch):
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")
    (started_in / "fixed").touch()

    result = no_input(runner, str(resume_runbook), "--no-input", "--no-step")

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("environment", [{}, {"RUNDOT_NO_INPUT": "1"}])
def test_no_input_cannot_pick_a_book(runner, monkeypatch, environment):
    """Picking a book is asking, so a runbook must be given."""
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    result = no_input(runner, *([] if environment else ["--no-input"]))

    assert result.exit_code == 2
    assert "give a runbook to run" in result.output


def test_a_run_that_needs_human_input_shows_it_at_the_end_without_no_input():
    """The printer's end box, for a prompter that can't answer even without --no-input."""
    console = Console(width=80, record=True, force_terminal=False)
    printer = cli._Printer(console)
    step = parse(RUNBOOKS / "needs-human-input-example.md").steps[1]

    printer(runner_module.RunFinished("needs_human_input", 1.0, step, block=step.blocks[0], message="Do it."))

    assert '⏸ needs human input at "Release notes"' in console.export_text()


# --- Printing events as JSON lines with --json ---


def json_lines(stdout: str) -> list[dict]:
    """Every line on stdout, parsed: each must be valid JSON, and nothing else may be there."""
    return [json.loads(line) for line in stdout.splitlines()]


def test_json_prints_one_object_per_event_and_nothing_else_on_stdout(runner, human_runbook, started_in, monkeypatch):
    monkeypatch.setenv("PR", "42")
    write_state(human_runbook, started_in, stopped="needs_human_input", step=1, block=0)

    result = runner.invoke(cli.cli, ["run", str(human_runbook), "--json"])

    assert result.exit_code == 0, result.output
    events = json_lines(result.stdout)
    assert [event["event"] for event in events] == [
        "overview",
        "step_started",
        "confirm",
        "confirm_answered",
        "step_started",
        "input_block",
        "input_collected",
        "block_started",
        "output",
        "block_finished",
        "run_finished",
    ]
    assert events[0]["resuming_at"] == 1
    assert events[0]["inputs"] == {"VERSION": "1.2.0"}
    assert events[1] == {"event": "step_started", "at": events[1]["at"], "number": 2, "name": "Release notes"}
    assert events[8]["text"] == "Announcing 1.2.0 in PR 42"
    assert events[-1]["status"] == "ok"
    assert all(set(event) >= {"event", "at"} for event in events)


def test_json_sends_everything_else_to_stderr(runner, human_runbook, started_in, monkeypatch):
    """resuming at, the transcript path and needs human input are text on stderr, so stdout stays JSON."""
    human_runbook.write_text(human_runbook.read_text().replace("---\n\n#", "output_path: run.log\n---\n\n#", 1))
    write_state(human_runbook, started_in, stopped="needs_human_input", step=1, block=0)

    result = runner.invoke(cli.cli, ["run", str(human_runbook), "--json"])

    assert result.exit_code == 3, result.output
    assert "resuming at 2/3 Release notes" in result.stderr
    assert "transcript: run.log" in result.stderr
    message = "set PR (The number GitHub gave the pull request) and run again."
    assert result.stderr.rstrip().splitlines()[-1] == f"needs human input: {message}"
    finished_event = json_lines(result.stdout)[-1]
    assert (finished_event["status"], finished_event["message"]) == ("needs_human_input", message)


def test_json_check_problems_go_to_stderr_with_nothing_on_stdout(runner, tmp_path):
    path = tmp_path / "broken.md"
    path.write_text("## No title\n\n```sh run\ntrue\n```\n")

    result = runner.invoke(cli.cli, ["run", str(path), "--json"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "error" in result.stderr


def test_json_missing_inputs_go_to_stderr(runner, resume_runbook, monkeypatch):
    monkeypatch.delenv("VERSION")

    result = runner.invoke(cli.cli, ["run", str(resume_runbook), "--json"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "missing inputs: VERSION, PUBLISH_TOKEN" in result.stderr


def test_json_masks_secrets_in_every_field(runner, resume_runbook, started_in, monkeypatch):
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")
    (started_in / "fixed").touch()

    result = runner.invoke(cli.cli, ["run", str(resume_runbook), "--json"])

    assert result.exit_code == 0, result.output
    assert "s3cret" not in result.stdout
    events = json_lines(result.stdout)
    assert events[0]["inputs"]["PUBLISH_TOKEN"] == "****"
    assert "Publishing 1.2.0 with ****" in [event.get("text") for event in events]


def test_json_never_asks_anything(runner, resume_runbook, started_in, monkeypatch):
    """--json implies --no-input, since a prompt would put text that isn't JSON on stdout."""
    fail_once(runner, resume_runbook)
    (started_in / "fixed").touch()
    monkeypatch.setenv("PUBLISH_TOKEN", "s3cret")

    result = runner.invoke(cli.cli, ["run", str(resume_runbook), "--json"])

    assert result.exit_code == 0, result.output
    assert "Start?" not in result.output
    assert "[r]esume" not in result.output
    assert json_lines(result.stdout)[0]["resuming_at"] == 2


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--json", "--dry"], "--json and --dry can't be used together"),
        (["--json", "--step"], "--json and --step can't be used together"),
    ],
)
def test_json_contradicting_flags_are_a_usage_error(runner, resume_runbook, arguments, message):
    result = runner.invoke(cli.cli, ["run", str(resume_runbook), *arguments])

    assert result.exit_code == 2
    assert message in result.output


def test_json_cannot_pick_a_book(runner, monkeypatch):
    monkeypatch.setenv("RUNDOT_LIBRARY", str(LIBRARY))

    result = runner.invoke(cli.cli, ["run", "--json"])

    assert result.exit_code == 2
    assert "--json can't pick a book from the library" in result.output


@pytest.mark.parametrize("reply", ["n", "x"])
def test_a_confirm_answered_no_is_asked_again_on_resume(runner, human_runbook, started_in, monkeypatch, reply):
    """Someone said no, so resuming must ask again rather than go ahead."""
    monkeypatch.setenv("PR", "42")
    first = runner.invoke(cli.cli, ["run", str(human_runbook)], input=f"y\n{reply}\n")
    assert finished(normalized(first.output)) == '✗ aborted at "Release notes"'

    result = runner.invoke(cli.cli, ["run", str(human_runbook)], input="r\ny\nn\n")

    assert result.exit_code == 1
    assert "Continue? [y/N]" in result.output
    assert finished(normalized(result.output)) == '✗ aborted at "Release notes"'


def test_a_confirm_after_a_failure_in_its_step_is_asked_again_on_resume(runner, tmp_path, started_in):
    path = write_runbook(tmp_path, "## A\n\n```confirm\nDo it.\n```\n\n```sh run\ntest -f fixed\n```\n")
    runner.invoke(cli.cli, ["run", str(path)], input="y\ny\n")
    (started_in / "fixed").touch()

    result = runner.invoke(cli.cli, ["run", str(path)], input="r\ny\ny\n")

    assert result.exit_code == 0, result.output
    assert "Continue? [y/N]" in result.output


def test_a_confirm_stopped_at_for_human_input_in_a_changed_step_is_asked_again(runner, tmp_path, started_in):
    """The step changed, so it runs again from its first block, and the confirm may not be the one that was done."""
    path = write_runbook(tmp_path, "## A\n\n```sh run\necho a\n```\n\n```confirm\nDo it.\n```\n")
    write_state(path, started_in, stopped="needs_human_input", step=0, block=1, inputs={})
    edit_step(path, "echo a", "echo b")

    result = runner.invoke(cli.cli, ["run", str(path)], input="r\ny\nn\n")

    assert result.exit_code == 1
    assert "Continue? [y/N]" in result.output
