import shlex
import subprocess
import sys
import tempfile
import warnings
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from paulrun.backends import Problem
from paulrun.inputs import PLACEHOLDER


class PythonBackend:
    """Runs each block as a Python script, with the runbook's python command or paulrun's own interpreter."""

    name = "python"
    languages = ("python", "py")

    def validate(self, code: str) -> list[Problem]:
        # Swap each placeholder for its bare name, which is a plain identifier wherever it appears, so the code
        # still compiles and keeps its line numbers. compile() uses paulrun's own interpreter, so syntax only the
        # runbook's python understands isn't caught.
        source = PLACEHOLDER.sub(lambda match: match.group(1), code)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", SyntaxWarning)
            try:
                compile(source, "<block>", "exec")
            except SyntaxError as e:
                return [Problem(e.msg, line=e.lineno)]
        return [
            Problem(str(warning.message), line=warning.lineno, warning=True)
            for warning in caught
            if issubclass(warning.category, SyntaxWarning)
        ]

    def run(
        self,
        code: str,
        *,
        frontmatter: Mapping[str, Any],
        env: Mapping[str, str],
        cwd: Path,
        output: Callable[[str], None],
    ) -> int:
        python = frontmatter.get("python")
        command = shlex.split(python) if isinstance(python, str) else [sys.executable]
        # A file rather than -c, so any interpreter command works, e.g. `uv run python`.
        with tempfile.TemporaryDirectory(prefix="paulrun-") as directory:
            script = Path(directory) / "block.py"
            script.write_text(code, encoding="utf-8")
            with subprocess.Popen(
                [*command, str(script)], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            ) as process:
                assert process.stdout is not None  # set because stdout is a pipe
                # Read bytes so only newlines split lines; text mode would also split on carriage returns.
                for raw in process.stdout:
                    output(raw.decode("utf-8", errors="replace").removesuffix("\n"))
        return process.returncode
