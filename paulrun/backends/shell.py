import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from paulrun.inputs import PLACEHOLDER


class ShellBackend:
    """Runs each block as one bash script that stops at the first failing command."""

    name = "shell"
    languages = ("sh", "bash", "shell")

    def validate(self, code: str) -> list[str]:
        # Bash reads <NAME> as a redirect, so swap each placeholder for its bare name, which is a plain word
        # wherever it appears. The script goes in on stdin because bash -c numbers lines from 0 on macOS.
        script = PLACEHOLDER.sub(lambda match: match.group(1), code)
        result = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True, errors="replace")
        if result.returncode == 0:
            return []
        problems = [line.removeprefix("bash: ") for line in result.stderr.splitlines() if line]
        return problems or [f"bash -n failed with exit code {result.returncode}"]

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
