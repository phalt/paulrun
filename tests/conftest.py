import pytest

from paulrun.backends import shell


@pytest.fixture
def without_shellcheck(monkeypatch):
    """Make the shell backend act as if shellcheck isn't installed, without changing PATH.

    shellcheck's findings depend on which version is installed, and CI has it while most laptops don't, so
    tests that check exact output use this. PATH is left alone, so bash and every other command are still
    found. shellcheck itself is tested with a stub in tests/backends/test_shell.py.
    """
    monkeypatch.setattr(shell, "_shellcheck", lambda: None)
