"""Tests for CLI commands."""

import importlib.metadata

import pytest
from click.testing import CliRunner

from paulrun import cli


@pytest.fixture
def runner():
    """Fixture providing a Click CLI test runner."""
    return CliRunner()


def test_version_prints_package_version(runner):
    """--version prints the version from the installed package metadata."""
    result = runner.invoke(cli.cli, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"paulrun, version {importlib.metadata.version('paulrun')}\n"


def test_help_lists_group_with_no_commands(runner):
    """--help shows the paulrun group, with no commands registered yet."""
    result = runner.invoke(cli.cli, ["--help"])

    assert result.exit_code == 0
    assert "Usage: paulrun" in result.output
    assert "Commands:" not in result.output
