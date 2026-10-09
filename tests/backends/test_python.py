"""Tests for the Python backend. Blocks really run under Python in tmp_path."""

import os
import shlex
import subprocess
import sys
import textwrap
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from paulrun.backends import Backend, Problem
from paulrun.backends.python import PythonBackend

# The runner sets this for every block, so Python's output isn't held back while it's piped.
UNBUFFERED = {**os.environ, "PYTHONUNBUFFERED": "1"}


def run(
    code: str, cwd: Path, env: Mapping[str, str] = UNBUFFERED, frontmatter: Mapping[str, Any] = {}
) -> tuple[list[str], int]:
    """Run a block with the Python backend and return the lines it printed and its exit code."""
    backend: Backend = PythonBackend()
    lines: list[str] = []
    exit_code = backend.run(code, frontmatter=frontmatter, env=env, cwd=cwd, output=lines.append)
    return lines, exit_code


def test_run_passes_each_line_to_output_and_returns_zero(tmp_path):
    """Each line goes to output without its newline, and a block that succeeds exits 0."""
    lines, exit_code = run("print('one')\nprint('two')\n", tmp_path)

    assert lines == ["one", "two"]
    assert exit_code == 0


def test_run_uses_paulruns_interpreter_when_the_runbook_sets_no_python(tmp_path):
    """With no python key in the frontmatter, blocks run with the interpreter that's running paulrun."""
    lines, _ = run("import sys\nprint(sys.executable)\n", tmp_path)

    assert lines == [sys.executable]


def test_run_uses_the_python_command_from_the_frontmatter(tmp_path):
    """The python key is split like a shell command, and the block's script is added as its last argument."""
    stub = tmp_path / "stub python"
    stub.write_text('#!/bin/sh\necho "args: $1"\ncat "$2"\n')
    stub.chmod(0o755)

    lines, exit_code = run("print('hi')\n", tmp_path, frontmatter={"python": f"{shlex.quote(str(stub))} --flag"})

    assert lines == ["args: --flag", "print('hi')"]
    assert exit_code == 0


def test_run_writes_each_block_to_a_script_that_is_deleted_afterwards(tmp_path):
    """The block runs as a .py file, which is gone once the block finishes."""
    lines, _ = run("print(__file__)\n", tmp_path)

    [script] = lines
    assert script.endswith(".py")
    assert not Path(script).exists()


def test_run_returns_the_exit_code_the_block_exits_with(tmp_path):
    """sys.exit ends the block, which exits with that code."""
    lines, exit_code = run("import sys\nprint('before')\nsys.exit(3)\nprint('after')\n", tmp_path)

    assert lines == ["before"]
    assert exit_code == 3


def test_run_block_that_raises_fails_with_its_traceback_in_output(tmp_path):
    """An uncaught exception exits 1, and its traceback is in the output because stderr is merged in."""
    lines, exit_code = run("raise ValueError('boom')\n", tmp_path)

    assert exit_code == 1
    assert lines[0] == "Traceback (most recent call last):"
    assert lines[-1] == "ValueError: boom"


def test_run_merges_stderr_into_output_in_order(tmp_path):
    """stdout and stderr share one stream, so lines keep the order they were printed in."""
    lines, _ = run("import sys\nprint('out')\nprint('err', file=sys.stderr)\nprint('out again')\n", tmp_path)

    assert lines == ["out", "err", "out again"]


def test_run_streams_output_as_it_is_printed(tmp_path):
    """Lines reach output while the block is still running, not all together when it finishes."""
    arrivals: list[float] = []

    PythonBackend().run(
        "import time\nprint('one')\ntime.sleep(0.5)\nprint('two')\n",
        frontmatter={},
        env=UNBUFFERED,
        cwd=tmp_path,
        output=lambda line: arrivals.append(time.monotonic()),
    )

    assert len(arrivals) == 2
    assert arrivals[1] - arrivals[0] >= 0.3


def test_run_passes_output_through_verbatim(tmp_path):
    """Only newlines split lines: carriage returns are kept, and bytes that aren't UTF-8 are replaced."""
    lines, exit_code = run("import sys\nsys.stdout.buffer.write(b'half\\rway\\nbad \\xff byte\\n')\n", tmp_path)

    assert lines == ["half\rway", "bad � byte"]
    assert exit_code == 0


def test_run_handles_code_and_output_that_are_not_ascii(tmp_path):
    """The script is written as UTF-8, so non-ASCII text in a block survives the round trip."""
    lines, _ = run("print('café ✓')\n", tmp_path)

    assert lines == ["café ✓"]


def test_run_uses_cwd(tmp_path):
    """The block runs in the directory it's given."""
    lines, _ = run("import os\nprint(os.getcwd())\n", tmp_path)

    assert lines == [str(tmp_path.resolve())]


def test_run_env_is_the_complete_environment(tmp_path, monkeypatch):
    """The block sees env and only env. paulrun's own environment isn't mixed in."""
    monkeypatch.setenv("PAULRUN_TEST_ONLY_IN_PARENT", "leaked")
    code = "import os\nprint(os.environ['GREETING'], os.environ.get('PAULRUN_TEST_ONLY_IN_PARENT', 'unset'))\n"

    lines, _ = run(code, tmp_path, env={"GREETING": "hello"})

    assert lines == ["hello unset"]


def test_run_reads_stdin_from_the_terminal(tmp_path):
    """stdin is inherited, so a block that reads input gets what was typed into paulrun's terminal."""
    script = textwrap.dedent(
        """\
        import os
        from pathlib import Path

        from paulrun.backends.python import PythonBackend

        lines = []
        code = 'print("got " + input())\\n'
        PythonBackend().run(code, frontmatter={}, env=os.environ, cwd=Path.cwd(), output=lines.append)
        print(lines)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script], input="typed\n", capture_output=True, text=True, cwd=tmp_path, check=True
    )

    assert result.stdout == "['got typed']\n"


def test_validate_accepts_valid_code():
    """A block Python can compile has no problems."""
    assert PythonBackend().validate("if True:\n    print('ok')\n") == []


def test_validate_reports_syntax_error_as_an_error_on_its_block_line():
    """A syntax error is an error, on its line counted from the top of the block."""
    problems = PythonBackend().validate("print('ok')\nif True\n    print('no colon')\n")

    assert problems == [Problem("expected ':'", line=2)]


def test_validate_reports_syntax_warnings_as_warnings():
    """Code that compiles but that Python warns about, such as an invalid escape, gets a warning."""
    problems = PythonBackend().validate('x = 1\npattern = "\\d+"\n')

    assert len(problems) == 1
    assert problems[0].line == 2
    assert problems[0].warning
    assert '"\\d" is an invalid escape sequence' in problems[0].message


def test_validate_accepts_placeholders():
    """<NAME> placeholders are allowed, even where Python would read < and > as comparisons."""
    assert PythonBackend().validate('version = "<VERSION>"\nprint(<COUNT> + 1)\n') == []


def test_validate_still_reports_errors_in_blocks_with_placeholders():
    """Replacing placeholders doesn't hide a real syntax error elsewhere, or move its line number."""
    problems = PythonBackend().validate('version = "<VERSION>"\nprint(<VERSION>\n\n')

    assert [problem.line for problem in problems] == [2]
    assert not problems[0].warning


def test_validate_does_not_run_the_block(tmp_path):
    """Validation only compiles the block."""
    created = tmp_path / "created"

    assert PythonBackend().validate(f"open({str(created)!r}, 'w')\n") == []
    assert not created.exists()
