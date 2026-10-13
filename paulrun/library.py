from collections.abc import Mapping
from pathlib import Path

LIBRARY_VARIABLE = "PAULRUN_LIBRARY"


def location(env: Mapping[str, str]) -> Path:
    """Where the runbook library is: PAULRUN_LIBRARY if it's set and not empty, otherwise ~/runbooks."""
    # An empty variable counts as unset, the same as for inputs, so a stray `PAULRUN_LIBRARY=` uses the default.
    if value := env.get(LIBRARY_VARIABLE):
        return Path(value).expanduser()
    return Path.home() / "runbooks"


def find(argument: str, cwd: Path, library: Path) -> Path | None:
    """The runbook an argument names, or None if there isn't one.

    A file that exists, relative to cwd, is used as it was written. Otherwise an argument with no / is a
    book's name, with or without .md, and is the file of that name directly inside the library.
    """
    path = Path(argument)
    if (cwd / path).is_file():
        return path
    if "/" in argument:
        return None
    book = library / (argument if argument.endswith(".md") else f"{argument}.md")
    return book if book.is_file() else None
