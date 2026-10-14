from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from paulrun.runbook import RunbookError, read_frontmatter

LIBRARY_VARIABLE = "PAULRUN_LIBRARY"


@dataclass(frozen=True)
class Book:
    """A runbook in the library, as listed: its name, and what its frontmatter says it is."""

    name: str  # the file name without .md, which is how it's run
    path: Path
    title: str | None  # None if it has no title, or it can't be read
    description: str | None
    problem: str | None = None  # why its frontmatter can't be read, if it can't


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


def books(library: Path) -> list[Book]:
    """Every book in the library, in name order: each .md file directly inside it. None if it doesn't exist.

    Only frontmatter is read, so a broken body doesn't hide a book, and one whose frontmatter can't be read
    is still listed, with the reason.
    """
    if not library.is_dir():
        return []
    return [_book(path) for path in sorted(library.glob("*.md")) if path.is_file()]


def _book(path: Path) -> Book:
    try:
        frontmatter = read_frontmatter(path)
    except (RunbookError, OSError) as e:
        # An OSError's strerror is the reason alone, e.g. "Permission denied", without the path repeated.
        problem = (e.strerror if isinstance(e, OSError) else None) or str(e)
        return Book(path.stem, path, None, None, problem=problem)
    # Only strings are shown, as for a parsed runbook; check reports a title or description of the wrong type.
    title, description = (frontmatter.get(key) for key in ("title", "description"))
    return Book(
        path.stem,
        path,
        title if isinstance(title, str) else None,
        description if isinstance(description, str) else None,
    )
