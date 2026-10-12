import importlib.metadata
import os
import signal
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any, Protocol

ENTRY_POINT_GROUP = "paulrun.backends"


@dataclass(frozen=True)
class Problem:
    """Something a backend found wrong with a block."""

    message: str
    line: int | None = None  # line in the block, counting its first line as 1; None if it's about the whole block
    warning: bool = False  # warnings are reported but don't stop the runbook running


class Backend(Protocol):
    """Runs `run` blocks for one or more languages.

    Backends are classes registered under the `paulrun.backends` entry point group. Each is created
    once, with no arguments, when backends are loaded.
    """

    # Read-only, so a backend can set them as plain class attributes.
    @property
    def name(self) -> str: ...

    @property
    def languages(self) -> tuple[str, ...]:
        """The fence languages this backend runs, e.g. ("sh", "bash")."""

    def validate(self, code: str) -> list[Problem]:
        """Return the problems found in a block, without running it. An empty list means it's fine.

        code is the block as written, so it can contain <NAME> placeholders. Replacing them with
        something this language accepts is up to the backend. Any error stops the runbook running;
        warnings are only reported.
        """

    def run(
        self,
        code: str,
        *,
        frontmatter: Mapping[str, Any],
        env: Mapping[str, str],
        cwd: Path,
        output: Callable[[str], None],
    ) -> int:
        """Run a block and return its exit code, where 0 means it succeeded.

        Call output with each line the block prints, without its newline, as soon as it's printed.
        Don't print anything directly; paulrun owns the terminal. frontmatter is the runbook's
        frontmatter, read-only. env is the block's complete environment and cwd is where it runs.
        """


class Interrupted(KeyboardInterrupt):
    """Ctrl-C was pressed while a block ran. The block has exited, with exit_code."""

    def __init__(self, exit_code: int):
        super().__init__(exit_code)
        self.exit_code = exit_code


def stream(command: Sequence[str], *, env: Mapping[str, str], cwd: Path, output: Callable[[str], None]) -> int:
    """Run command, passing each line it prints to output as it's printed, and return its exit code.

    stdout and stderr are merged, so lines keep the order they were printed in. The command shares
    paulrun's terminal, so it can still ask for a password on it, as git, ssh and gpg do. This is how
    the built-in backends run blocks, and other backends can use it too.

    Ctrl-C reaches the command as well as paulrun. On the first press, paulrun waits for the command to
    stop, still passing on what it prints. A second press kills it and everything it started, and stops
    reading, so nothing can keep paulrun waiting. Either way, once the command has exited, Interrupted
    is raised with its exit code.
    """
    interrupted = False
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        assert process.stdout is not None  # set because stdout is a pipe
        while True:
            try:
                # Read bytes so only newlines split lines; text mode would also split on carriage returns.
                for raw in process.stdout:
                    output(raw.decode("utf-8", errors="replace").removesuffix("\n"))
                break
            except KeyboardInterrupt:
                if not interrupted:
                    # The terminal sent Ctrl-C to the command too, so let it stop in its own way.
                    interrupted = True
                    continue
                _kill_tree(process.pid)
                # Stop reading, so nothing still holding the output open can keep paulrun waiting.
                process.stdout.close()
                break
        process.wait()
    if interrupted:
        raise Interrupted(process.returncode)
    return process.returncode


def _kill_tree(pid: int) -> None:
    """Kill a process and every process it started, however deep.

    Each one is stopped first, so none can start another between being found and being killed.
    """
    found = [pid]
    for parent in found:
        _signal(parent, signal.SIGSTOP)
        found.extend(child for child in _children(parent) if child not in found)
    for process in found:
        _signal(process, signal.SIGKILL)


def _children(pid: int) -> list[int]:
    """The processes pid started that are still running."""
    listing = subprocess.run(["ps", "-A", "-o", "pid=", "-o", "ppid="], capture_output=True, text=True).stdout
    return [int(child) for child, parent in (row.split() for row in listing.splitlines()) if int(parent) == pid]


def _signal(pid: int, signal_number: int) -> None:
    """Signal a process, unless it has already gone."""
    try:
        os.kill(pid, signal_number)
    except ProcessLookupError:
        pass


class BackendError(Exception):
    """Backends can't be loaded, e.g. two of them claim the same language."""


@dataclass(frozen=True)
class LoadedBackend:
    backend: Backend
    entry_point: EntryPoint  # where it was registered, e.g. paulrun's own pyproject.toml or another package's


def installed_entry_points() -> Iterable[EntryPoint]:
    """Every backend registered under the paulrun.backends group by an installed package, paulrun included."""
    return importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)


def load_backend_sources(entry_points: Iterable[EntryPoint] | None = None) -> list[LoadedBackend]:
    """Load each backend once, with where it came from, from the installed entry points unless others are given.

    Raises BackendError if two backends claim the same language.
    """
    if entry_points is None:
        entry_points = installed_entry_points()
    loaded: list[LoadedBackend] = []
    claimed: dict[str, LoadedBackend] = {}
    for entry_point in entry_points:
        source = LoadedBackend(entry_point.load()(), entry_point)
        for language in source.backend.languages:
            if language in claimed:
                other = claimed[language]
                raise BackendError(
                    f"language {language!r} is claimed by both {other.backend.name!r} ({other.entry_point.value}) "
                    f"and {source.backend.name!r} ({entry_point.value})"
                )
            claimed[language] = source
        loaded.append(source)
    return loaded


def load_backends(entry_points: Iterable[EntryPoint] | None = None) -> dict[str, Backend]:
    """Load backends keyed by language, from the installed entry points unless others are given."""
    return {
        language: source.backend
        for source in load_backend_sources(entry_points)
        for language in source.backend.languages
    }
