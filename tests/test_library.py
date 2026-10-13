"""Tests for the runbook library: where it is, and finding a book in it by name."""

from pathlib import Path

import pytest

from paulrun import library
from paulrun.backends import load_backends
from paulrun.runbook import parse
from paulrun.validate import validate

# A fixture library of readable example books, for the tests of looking up, listing and picking books.
LIBRARY = Path(__file__).parent / "library"


@pytest.mark.parametrize("book", sorted(LIBRARY.glob("*.md")), ids=lambda path: path.name)
def test_every_book_in_the_fixture_library_passes_check(book, without_shellcheck):
    """Each book is an example of a runbook kept in a library, so it's written the way one should be."""
    findings = validate(parse(book), load_backends()).findings

    assert [f"{finding.line}: {finding.message}" for finding in findings] == []


def write(path: Path, text: str = "---\ntitle: T\n---\n") -> Path:
    """Write a file, creating its directory, and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_location_is_paulrun_library_when_it_is_set(tmp_path):
    """PAULRUN_LIBRARY says where the library is."""
    assert library.location({"PAULRUN_LIBRARY": str(tmp_path / "books")}) == tmp_path / "books"


def test_location_expands_a_tilde_in_paulrun_library(tmp_path, monkeypatch):
    """PAULRUN_LIBRARY=~/work-runbooks means the folder in your home directory, even when the shell didn't expand it."""
    monkeypatch.setenv("HOME", str(tmp_path))

    assert library.location({"PAULRUN_LIBRARY": "~/work-runbooks"}) == tmp_path / "work-runbooks"


@pytest.mark.parametrize("env", [{}, {"PAULRUN_LIBRARY": ""}], ids=["unset", "empty"])
def test_location_is_runbooks_in_the_home_directory_by_default(env, tmp_path, monkeypatch):
    """Without PAULRUN_LIBRARY, or with it empty, the library is ~/runbooks."""
    monkeypatch.setenv("HOME", str(tmp_path))

    assert library.location(env) == tmp_path / "runbooks"


def test_find_gives_a_file_that_exists_as_it_was_written(tmp_path):
    """A path to a file is used as it is, relative to cwd, the same as before there was a library."""
    write(tmp_path / "project" / "RELEASING.md")

    assert library.find("RELEASING.md", tmp_path / "project", tmp_path / "library") == Path("RELEASING.md")


def test_find_looks_up_a_name_in_the_library(tmp_path):
    """A name that isn't a file here is the book of that name in the library."""
    book = write(tmp_path / "library" / "rebuild-frontend.md")

    assert library.find("rebuild-frontend", tmp_path / "project", tmp_path / "library") == book


def test_find_allows_a_book_name_ending_in_md(tmp_path):
    """rebuild-frontend.md finds the same book as rebuild-frontend."""
    book = write(tmp_path / "library" / "rebuild-frontend.md")

    assert library.find("rebuild-frontend.md", tmp_path / "project", tmp_path / "library") == book


def test_find_uses_a_file_here_before_a_book_of_the_same_name(tmp_path):
    """Paths win over names, so a runbook in the project is never hidden by one in the library."""
    write(tmp_path / "project" / "deploy.md")
    write(tmp_path / "library" / "deploy.md")

    assert library.find("deploy.md", tmp_path / "project", tmp_path / "library") == Path("deploy.md")


def test_find_never_looks_in_the_library_for_an_argument_with_a_slash(tmp_path):
    """docs/deploy.md is only ever a path, so a typo in a path can't quietly run a book instead."""
    write(tmp_path / "library" / "deploy.md")

    assert library.find("docs/deploy.md", tmp_path / "project", tmp_path / "library") is None


def test_find_treats_a_directory_as_not_a_runbook(tmp_path):
    """A folder here with a book's name doesn't hide the book."""
    (tmp_path / "project" / "deploy").mkdir(parents=True)
    book = write(tmp_path / "library" / "deploy.md")

    assert library.find("deploy", tmp_path / "project", tmp_path / "library") == book


def test_find_only_takes_books_that_are_files(tmp_path):
    """A folder in the library named like a book isn't one."""
    (tmp_path / "library" / "deploy.md").mkdir(parents=True)

    assert library.find("deploy", tmp_path / "project", tmp_path / "library") is None


def test_find_gives_none_when_there_is_no_such_file_or_book(tmp_path):
    """Nothing by that name here or in the library, including when there's no library at all."""
    assert library.find("missing", tmp_path / "project", tmp_path / "no-library") is None


def test_find_never_looks_outside_the_library_for_a_book(tmp_path):
    """A name can't climb out of the library, since anything with a / is a path, and .. alone is a directory."""
    write(tmp_path / "secret.md")
    (tmp_path / "library").mkdir()

    assert library.find("..", tmp_path / "project", tmp_path / "library") is None
