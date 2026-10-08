import importlib.metadata
from collections.abc import Callable, Iterable, Mapping
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any, Protocol

ENTRY_POINT_GROUP = "paulrun.backends"


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

    def validate(self, code: str) -> list[str]:
        """Return the problems found in a block, without running it. An empty list means it's fine.

        code is the block as written, so it can contain <NAME> placeholders. Replacing them with
        something this language accepts is up to the backend.
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


class BackendError(Exception):
    """Backends can't be loaded, e.g. two of them claim the same language."""


def load_backends(entry_points: Iterable[EntryPoint] | None = None) -> dict[str, Backend]:
    """Load backends keyed by language, from the installed entry points unless others are given."""
    if entry_points is None:
        entry_points = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    loaded: dict[str, tuple[Backend, EntryPoint]] = {}
    for entry_point in entry_points:
        backend: Backend = entry_point.load()()
        for language in backend.languages:
            if language in loaded:
                other, other_entry_point = loaded[language]
                raise BackendError(
                    f"language {language!r} is claimed by both {other.name!r} ({other_entry_point.value}) "
                    f"and {backend.name!r} ({entry_point.value})"
                )
            loaded[language] = (backend, entry_point)
    return {language: backend for language, (backend, _) in loaded.items()}
