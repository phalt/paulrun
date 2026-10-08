"""Tests for the shell backend. Blocks really run under bash in tmp_path."""

import os
import subprocess
import sys
import textwrap
import time
from collections.abc import Mapping
from pathlib import Path

from paulrun.backends import Backend
from paulrun.backends.shell import ShellBackend


def run(code: str, cwd: Path, env: Mapping[str, str] = os.environ) -> tuple[list[str], int]:
    """Run a block with the shell backend and return the lines it printed and its exit code."""
    backend: Backend = ShellBackend()
    lines: list[str] = []
    exit_code = backend.run(code, frontmatter={}, env=env, cwd=cwd, output=lines.append)
    return lines, exit_code


def test_run_passes_each_line_to_output_and_returns_zero(tmp_path):
    """Each line goes to output without its newline, and a block that succeeds exits 0."""
    lines, exit_code = run("echo one\necho two\n", tmp_path)

    assert lines == ["one", "two"]
    assert exit_code == 0


def test_run_merges_stderr_into_output_in_order(tmp_path):
    """stdout and stderr share one stream, so lines keep the order they were printed in."""
    lines, _ = run("echo out\necho err >&2\necho out again\n", tmp_path)

    assert lines == ["out", "err", "out again"]


def test_run_keeps_last_line_without_newline(tmp_path):
    """Output that doesn't end in a newline still reaches output."""
    lines, _ = run("printf 'first\\nlast'\n", tmp_path)

    assert lines == ["first", "last"]


def test_run_passes_output_through_verbatim(tmp_path):
    """Only newlines split lines. Blank lines, leading spaces and carriage returns are kept."""
    lines, _ = run("printf '  indented\\n\\nhalf\\rway\\n'\n", tmp_path)

    assert lines == ["  indented", "", "half\rway"]


def test_run_replaces_output_that_is_not_utf8(tmp_path):
    """A command printing bytes that aren't UTF-8 can't break the run."""
    lines, exit_code = run("printf 'bad \\377 byte\\n'\n", tmp_path)

    assert lines == ["bad � byte"]
    assert exit_code == 0


def test_run_streams_output_as_it_is_printed(tmp_path):
    """Lines reach output while the block is still running, not all together when it finishes."""
    arrivals: list[float] = []

    ShellBackend().run(
        "echo one\nsleep 0.5\necho two\n",
        frontmatter={},
        env=os.environ,
        cwd=tmp_path,
        output=lambda line: arrivals.append(time.monotonic()),
    )

    assert len(arrivals) == 2
    assert arrivals[1] - arrivals[0] >= 0.3


def test_run_is_one_script(tmp_path):
    """The block runs as one script, so a variable set on one line is still set on the next."""
    lines, _ = run('greeting=hello\necho "$greeting"\n', tmp_path)

    assert lines == ["hello"]


def test_run_stops_at_failing_command_with_its_exit_code(tmp_path):
    """A failing command ends the block, which exits with that command's exit code."""
    lines, exit_code = run("echo before\nsh -c 'exit 3'\necho after\n", tmp_path)

    assert lines == ["before"]
    assert exit_code == 3


def test_run_catches_failure_inside_a_pipe(tmp_path):
    """A failure early in a pipe fails the block, even though the last command in the pipe succeeds."""
    lines, exit_code = run("sh -c 'exit 4' | cat\necho after\n", tmp_path)

    assert lines == []
    assert exit_code == 4


def test_run_uses_cwd(tmp_path):
    """The block runs in the directory it's given."""
    lines, _ = run("pwd -P\n", tmp_path)

    assert lines == [str(tmp_path.resolve())]


def test_run_uses_env(tmp_path):
    """The block can read variables from env."""
    lines, _ = run('echo "$GREETING"\n', tmp_path, env={**os.environ, "GREETING": "hello"})

    assert lines == ["hello"]


def test_run_env_is_the_complete_environment(tmp_path, monkeypatch):
    """Only env reaches the block. paulrun's own environment isn't mixed in."""
    monkeypatch.setenv("PAULRUN_TEST_ONLY_IN_PARENT", "leaked")

    lines, _ = run('echo "${PAULRUN_TEST_ONLY_IN_PARENT:-unset}"\n', tmp_path, env={"PATH": os.environ["PATH"]})

    assert lines == ["unset"]


def test_run_reads_stdin_from_the_terminal(tmp_path):
    """stdin is inherited, so a block that reads input gets what was typed into paulrun's terminal."""
    script = textwrap.dedent(
        """\
        import os
        from pathlib import Path

        from paulrun.backends.shell import ShellBackend

        lines = []
        code = 'read answer\\necho "got $answer"\\n'
        ShellBackend().run(code, frontmatter={}, env=os.environ, cwd=Path.cwd(), output=lines.append)
        print(lines)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script], input="typed\n", capture_output=True, text=True, cwd=tmp_path, check=True
    )

    assert result.stdout == "['got typed']\n"


def test_validate_accepts_valid_code():
    """A block bash can parse has no problems."""
    assert ShellBackend().validate("if true; then\n  echo ok\nfi\n") == []


def test_validate_reports_syntax_error_with_block_line():
    """A syntax error is reported with its line, counted from the top of the block."""
    problems = ShellBackend().validate("echo ok\nif true; then\nfi\n")

    assert problems
    assert problems[0].startswith("line 3: syntax error")


def test_validate_accepts_placeholders():
    """<NAME> placeholders are allowed, even where bash would read them as a redirect."""
    assert ShellBackend().validate("git tag <VERSION>\ngit push origin <VERSION>\n") == []


def test_validate_still_reports_errors_in_blocks_with_placeholders():
    """Replacing placeholders doesn't hide a real syntax error elsewhere, or move its line number."""
    problems = ShellBackend().validate("git tag <VERSION>\nif true; then\nfi\n")

    assert problems
    assert problems[0].startswith("line 3: syntax error")


def test_validate_does_not_run_the_block(tmp_path):
    """Validation only parses the block."""
    created = tmp_path / "created"

    assert ShellBackend().validate(f"touch {created}\n") == []
    assert not created.exists()
