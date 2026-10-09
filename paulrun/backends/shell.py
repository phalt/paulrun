import json
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from paulrun.backends import Problem
from paulrun.inputs import PLACEHOLDER

# How bash -n reports each problem, e.g. "bash: line 3: syntax error near unexpected token `fi'".
_BASH_ERROR = re.compile(r"^\S*bash: line (\d+): (.*)$")


class ShellBackend:
    """Runs each block as one bash script that stops at the first failing command."""

    name = "shell"
    languages = ("sh", "bash", "shell")

    def validate(self, code: str) -> list[Problem]:
        # Bash reads <NAME> as a redirect, so swap each placeholder for its bare name, which is a plain word
        # wherever it appears.
        script = PLACEHOLDER.sub(lambda match: match.group(1), code)
        return _bash_errors(script) or _shellcheck_warnings(script)

    def run(
        self,
        code: str,
        *,
        frontmatter: Mapping[str, Any],
        env: Mapping[str, str],
        cwd: Path,
        output: Callable[[str], None],
    ) -> int:
        # The flags match `set -eo pipefail` without adding a line, so the script bash runs is exactly the
        # block. The last argument is $0, which bash puts at the start of its error messages.
        command = ["bash", "-e", "-o", "pipefail", "-c", code, "paulrun"]
        with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
            assert process.stdout is not None  # set because stdout is a pipe
            # Read bytes so only newlines split lines; text mode would also split on carriage returns.
            for raw in process.stdout:
                output(raw.decode("utf-8", errors="replace").removesuffix("\n"))
        return process.returncode


def _bash_errors(script: str) -> list[Problem]:
    # The script goes in on stdin because bash -c numbers lines from 0 on macOS.
    result = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True, errors="replace")
    if result.returncode == 0:
        return []
    problems = []
    for line in result.stderr.splitlines():
        if match := _BASH_ERROR.match(line):
            number, message = int(match.group(1)), match.group(2)
            # After a syntax error bash prints the offending source line in quotes, which adds nothing.
            if problems and problems[-1].line == number and message.startswith("`") and message.endswith("'"):
                continue
            problems.append(Problem(message, line=number))
        elif line:
            problems.append(Problem(line))
    return problems or [Problem(f"bash -n failed with exit code {result.returncode}")]


def _shellcheck_warnings(script: str) -> list[Problem]:
    """shellcheck's findings, all as warnings, or nothing if shellcheck isn't installed."""
    if shutil.which("shellcheck") is None:
        return []
    result = subprocess.run(
        ["shellcheck", "--shell=bash", "--format=json", "-"], input=script, capture_output=True, text=True
    )
    try:
        findings = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [Problem(f"shellcheck failed: {result.stderr.strip() or result.stdout.strip()}", warning=True)]
    return [
        Problem(f"SC{finding['code']}: {finding['message']}", line=finding["line"], warning=True)
        for finding in findings
    ]
