"""Tests that the example runbooks, and the one paulrun releases itself with, are valid and do what they say."""

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from markdown_it import MarkdownIt

from paulrun import cli
from paulrun.backends import load_backends
from paulrun.runbook import parse
from paulrun.validate import validate

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
RUNBOOKS = sorted(EXAMPLES.glob("*.md")) + [ROOT / "PUBLISHING.md"]
RELEASES = [EXAMPLES / "clientele-publishing.md", ROOT / "PUBLISHING.md"]


@pytest.fixture
def runner(monkeypatch):
    """Fixture providing a Click CLI test runner, with plain output even if the environment forces colour."""
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    return CliRunner()


def test_there_are_examples():
    """The examples this file tests are all there, so a renamed one can't quietly go untested."""
    assert [path.name for path in RUNBOOKS] == ["clientele-publishing.md", "hello.md", "PUBLISHING.md"]


@pytest.mark.parametrize("path", RUNBOOKS, ids=lambda path: path.name)
def test_every_example_passes_check(path, without_shellcheck):
    """Each example has no errors and no warnings, so it shows a runbook written the way it should be."""
    findings = validate(parse(path), load_backends()).findings

    assert [f"{finding.line}: {finding.message}" for finding in findings] == []


def test_hello_is_the_readme_example():
    """examples/hello.md is the runbook in the README, so the two can't drift apart."""
    tokens = MarkdownIt("commonmark").parse((ROOT / "README.md").read_text())
    [readme] = [token.content for token in tokens if token.type == "fence" and token.info == "markdown"]

    assert (EXAMPLES / "hello.md").read_text() == readme


def test_hello_runs_end_to_end(runner, monkeypatch):
    """go runs hello.md's shell and Python blocks with the name it asks for."""
    monkeypatch.delenv("NAME", raising=False)

    result = runner.invoke(cli.cli, ["go", str(EXAMPLES / "hello.md")], input="Paul\ny\n")

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "Hello, Paul!" in lines
    assert "Paul has 4 letters" in lines
    assert lines[-1].startswith("finished: ok")


@pytest.mark.parametrize("path", RELEASES, ids=lambda path: path.name)
def test_a_dry_release_shows_every_step_for_the_version(path, runner, tmp_path, monkeypatch):
    """--dry on a release shows each step with the version filled in, never asks for the token, and writes nothing.

    It runs on a copy in tmp_path, so even a --dry that ran something couldn't touch a real repository.
    """
    copy = Path(shutil.copy(path, tmp_path))
    monkeypatch.setenv("VERSION", "9.9.9")
    monkeypatch.delenv("UV_PUBLISH_TOKEN", raising=False)

    result = runner.invoke(cli.cli, ["go", "--dry", str(copy)])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "inputs: VERSION=9.9.9 UV_PUBLISH_TOKEN=****" in lines
    for step in parse(path).steps:
        assert f"=== {step.name} ===" in lines
    assert "    git tag 9.9.9" in lines
    assert "    git push origin 9.9.9" in lines
    assert any("releases/new?tag=9.9.9" in line for line in lines)
    assert "<VERSION>" not in result.output
    assert lines[-1] == "finished: dry run, nothing was run"
    assert sorted(path.name for path in tmp_path.iterdir()) == [copy.name]
