from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from paulrun import cli
from paulrun.backends import shell


@pytest.fixture(autouse=True)
def started_in(tmp_path_factory, monkeypatch) -> Path:
    """Start every test in its own empty directory, and return it.

    Blocks run in the directory paulrun is started from, so a test started in the repository could change it.
    This is a different directory from tmp_path, so a test can keep its runbook apart from where it runs.
    """
    directory = tmp_path_factory.mktemp("started-in")
    monkeypatch.chdir(directory)
    return directory


# The time every LOG line shows in tests, as cli.log_start writes it.
LOG_AT = datetime(2026, 11, 4, 10, 2, 13, 482915, tzinfo=timezone(timedelta(hours=1)))
LOG_LINE = cli.log_start(LOG_AT)


@pytest.fixture(autouse=True)
def fixed_log_time(monkeypatch) -> None:
    """Stop the clock for the LOG lines, so tests can match output exactly."""
    monkeypatch.setattr(cli, "_now", lambda: LOG_AT)


@pytest.fixture(autouse=True)
def empty_library(tmp_path_factory, monkeypatch) -> Path:
    """Point PAULRUN_LIBRARY at an empty directory for every test, and return it.

    So a real library at ~/runbooks never changes what a test sees. A test that needs books sets PAULRUN_LIBRARY
    itself, usually to tests/library.
    """
    directory = tmp_path_factory.mktemp("library")
    monkeypatch.setenv("PAULRUN_LIBRARY", str(directory))
    return directory


@pytest.fixture
def without_shellcheck(monkeypatch):
    """Make the shell backend act as if shellcheck isn't installed, without changing PATH.

    shellcheck's findings depend on which version is installed, and CI has it while most laptops don't, so
    tests that check exact output use this. PATH is left alone, so bash and every other command are still
    found. shellcheck itself is tested with a stub in tests/backends/test_shell.py.
    """
    monkeypatch.setattr(shell, "_shellcheck", lambda: None)
