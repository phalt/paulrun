"""Tests for the runbook library: where it is, finding a book in it by name, and listing its books."""

import os
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


def test_books_reads_each_books_name_title_and_description_in_name_order(tmp_path):
    """Each book is named for its file, and described by its frontmatter."""
    write(tmp_path / "update-deps.md", "---\ntitle: Update dependencies\ndescription: Upgrade, then test.\n---\n")
    write(tmp_path / "deploy.md", "---\ntitle: Deploy\n---\n")

    assert library.books(tmp_path) == [
        library.Book("deploy", tmp_path / "deploy.md", "Deploy", None),
        library.Book("update-deps", tmp_path / "update-deps.md", "Update dependencies", "Upgrade, then test."),
    ]


def test_books_reads_only_the_frontmatter(tmp_path):
    """A book whose body is broken, or isn't even UTF-8, is still listed by its frontmatter."""
    write(tmp_path / "broken-body.md", "---\ntitle: Broken body\n---\n\n## Step\n").open("ab").write(b"\xff\xfe\n")

    assert library.books(tmp_path) == [library.Book("broken-body", tmp_path / "broken-body.md", "Broken body", None)]


def test_books_keeps_a_book_whose_frontmatter_cannot_be_read_with_the_reason(tmp_path):
    """A book with broken frontmatter is listed with why it can't be read, so it isn't silently missing."""
    write(tmp_path / "unclosed.md", "---\ntitle: Unclosed\n\n## Step\n")

    assert library.books(tmp_path) == [
        library.Book("unclosed", tmp_path / "unclosed.md", None, None, problem="frontmatter has no closing ---")
    ]


def test_books_keeps_a_book_it_cannot_open_with_the_reason(tmp_path):
    """A book paulrun can't open, e.g. one it isn't allowed to read, is listed with the reason too."""
    locked = write(tmp_path / "locked.md")
    locked.chmod(0)
    if os.access(locked, os.R_OK):  # e.g. running as root, which can read anything
        pytest.skip("files can't be made unreadable here")

    [book] = library.books(tmp_path)

    assert book.name == "locked"
    assert book.problem == "Permission denied"


def test_books_leaves_out_titles_and_descriptions_that_are_not_strings(tmp_path):
    """A title or description of the wrong type isn't shown; check reports it."""
    write(tmp_path / "odd.md", "---\ntitle: [a, list]\ndescription: 3\n---\n")

    assert library.books(tmp_path) == [library.Book("odd", tmp_path / "odd.md", None, None)]


def test_books_ignores_subfolders_and_files_that_are_not_markdown(tmp_path):
    """Only .md files directly in the library are books, so ~/runbooks/logs/ can hold transcripts."""
    write(tmp_path / "deploy.md")
    write(tmp_path / "logs" / "release-1.2.0.md")
    write(tmp_path / "notes.txt")
    (tmp_path / "folder.md").mkdir()

    assert [book.name for book in library.books(tmp_path)] == ["deploy"]


def test_books_is_empty_for_a_library_that_does_not_exist(tmp_path):
    """No library yet just means no books."""
    assert library.books(tmp_path / "runbooks") == []
