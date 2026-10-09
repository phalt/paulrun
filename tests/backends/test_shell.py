"""Tests for the shell backend. Blocks really run under bash in tmp_path."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

from paulrun.backends import Backend, Problem
from paulrun.backends.shell import ShellBackend


@pytest.fixture
def no_shellcheck(monkeypatch, tmp_path_factory):
    """A PATH with bash but no shellcheck, so validation is just bash -n, whether or not shellcheck is installed."""
    bin_dir = tmp_path_factory.mktemp("bin")
    (bin_dir / "bash").symlink_to(shutil.which("bash"))
    monkeypatch.setenv("PATH", str(bin_dir))


@pytest.fixture
def fake_shellcheck(monkeypatch, tmp_path_factory):
    """Put a stub shellcheck first on PATH. Call it with the findings it should print as JSON.

    The stub writes the arguments and script it was given to the returned file.
    """
    bin_dir = tmp_path_factory.mktemp("bin")
    record = bin_dir / "record.txt"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    def install(findings: list[dict]) -> Path:
        script = bin_dir / "shellcheck"
        script.write_text(
            "#!/bin/sh\n"
            f'{{ echo "args: $*"; printf "script: "; cat; }} > {shlex.quote(str(record))}\n'
            f"echo {shlex.quote(json.dumps(findings))}\n"
            # shellcheck exits 1 when it has findings, which isn't a failure to run.
            f"exit {1 if findings else 0}\n"
        )
        script.chmod(0o755)
        return record

    return install


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


def test_validate_accepts_valid_code(no_shellcheck):
    """A block bash can parse has no problems."""
    assert ShellBackend().validate("if true; then\n  echo ok\nfi\n") == []


def test_validate_reports_syntax_error_as_an_error_on_its_block_line(no_shellcheck):
    """A syntax error is an error, on its line counted from the top of the block, without bash's name in front."""
    problems = ShellBackend().validate("echo ok\nif true; then\nfi\n")

    assert problems == [Problem("syntax error near unexpected token `fi'", line=3)]


def test_validate_reports_each_error_bash_finds(no_shellcheck):
    """Every message bash prints is kept, each on its own line."""
    problems = ShellBackend().validate('echo "unclosed\n')

    assert problems == [
        Problem("unexpected EOF while looking for matching `\"'", line=1),
        Problem("syntax error: unexpected end of file", line=2),
    ]


def test_validate_accepts_placeholders(no_shellcheck):
    """<NAME> placeholders are allowed, even where bash would read them as a redirect."""
    assert ShellBackend().validate("git tag <VERSION>\ngit push origin <VERSION>\n") == []


def test_validate_still_reports_errors_in_blocks_with_placeholders(no_shellcheck):
    """Replacing placeholders doesn't hide a real syntax error elsewhere, or move its line number."""
    problems = ShellBackend().validate("git tag <VERSION>\nif true; then\nfi\n")

    assert problems == [Problem("syntax error near unexpected token `fi'", line=3)]


def test_validate_does_not_run_the_block(tmp_path, no_shellcheck):
    """Validation only parses the block."""
    created = tmp_path / "created"

    assert ShellBackend().validate(f"touch {created}\n") == []
    assert not created.exists()


def test_validate_adds_shellcheck_findings_as_warnings(fake_shellcheck):
    """When shellcheck is installed, its findings are warnings on their block lines, with their codes."""
    fake_shellcheck(
        [
            {"line": 2, "level": "warning", "code": 2086, "message": "Double quote to prevent globbing."},
            {"line": 1, "level": "info", "code": 2164, "message": "Use cd ... || exit."},
        ]
    )

    problems = ShellBackend().validate("cd somewhere\necho $1\n")

    assert problems == [
        Problem("SC2086: Double quote to prevent globbing.", line=2, warning=True),
        Problem("SC2164: Use cd ... || exit.", line=1, warning=True),
    ]


def test_validate_runs_shellcheck_on_the_block_as_bash_with_placeholders_replaced(fake_shellcheck):
    """shellcheck checks the same script bash -n does, as bash, so it doesn't complain about a missing shebang."""
    record = fake_shellcheck([])

    ShellBackend().validate("git tag <VERSION>\n")

    assert record.read_text() == "args: --shell=bash --format=json -\nscript: git tag VERSION\n"


def test_validate_skips_shellcheck_when_bash_finds_errors(fake_shellcheck):
    """A script that doesn't parse only gets bash's errors, not shellcheck's view of the same mistake."""
    record = fake_shellcheck([{"line": 3, "level": "error", "code": 1089, "message": "Parsing stopped."}])

    problems = ShellBackend().validate("echo ok\nif true; then\nfi\n")

    assert problems == [Problem("syntax error near unexpected token `fi'", line=3)]
    assert not record.exists()


def test_validate_warns_when_shellcheck_cannot_check_the_block(monkeypatch, tmp_path):
    """If shellcheck is installed but doesn't give findings, that's a warning rather than a crash or an error."""
    (tmp_path / "shellcheck").write_text("#!/bin/sh\necho 'shellcheck: broken install' >&2\nexit 2\n")
    (tmp_path / "shellcheck").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    problems = ShellBackend().validate("echo ok\n")

    assert problems == [Problem("shellcheck failed: shellcheck: broken install", warning=True)]


def test_validate_keeps_bash_messages_it_cannot_read_a_line_number_from(monkeypatch, tmp_path):
    """A message from bash -n in an unexpected shape is still an error, on the whole block."""
    (tmp_path / "bash").write_text("#!/bin/sh\necho 'bash: some new complaint' >&2\nexit 2\n")
    (tmp_path / "bash").chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    problems = ShellBackend().validate("echo ok\n")

    assert problems == [Problem("bash: some new complaint")]


def test_validate_reports_a_bash_failure_that_prints_nothing(monkeypatch, tmp_path):
    """If bash -n fails without saying why, the block still gets an error."""
    (tmp_path / "bash").write_text("#!/bin/sh\nexit 2\n")
    (tmp_path / "bash").chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert ShellBackend().validate("echo ok\n") == [Problem("bash -n failed with exit code 2")]
