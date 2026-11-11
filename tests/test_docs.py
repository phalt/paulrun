"""Tests that the examples in the docs are real, valid runbooks, so the docs can't drift from the format."""

import inspect
import re
import shutil
import sys
import tomllib
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from click.testing import CliRunner
from markdown_it import MarkdownIt

from rundot import backends, cli
from rundot.backends import Backend, Problem, load_backends
from rundot.runbook import parse
from rundot.validate import validate
from tests.output import overview, printed

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node isn't installed")


@pytest.fixture
def runner(monkeypatch):
    """Fixture providing a Click CLI test runner, with plain output even if the environment forces colour."""
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    return CliRunner()


def fences(path: Path) -> list[tuple[str, str]]:
    """Each fenced code block in a markdown file, as its info string and its content."""
    tokens = MarkdownIt("commonmark").parse(path.read_text())
    return [(token.info, token.content) for token in tokens if token.type == "fence"]


def check_example(text: str, tmp_path: Path) -> list[str]:
    """Write a runbook from the docs to a file and return everything check finds in it."""
    path = tmp_path / "RELEASING.md"
    path.write_text(text)
    return [f"{finding.line}: {finding.message}" for finding in validate(parse(path), load_backends()).findings]


def test_the_home_page_example_runbook_is_valid(tmp_path, without_shellcheck):
    """The runbook on the home page passes check with no errors or warnings."""
    [example] = re.findall(r"^````markdown\n(.*?)^````$", (DOCS / "index.md").read_text(), re.MULTILINE | re.DOTALL)

    assert check_example(example, tmp_path) == []


def test_the_library_pages_worked_example_is_a_valid_book(tmp_path, without_shellcheck):
    """The library page's frontend rebuild passes check, and shows what the page says it does."""
    [example] = re.findall(r"^````markdown\n(.*?)^````$", (DOCS / "library.md").read_text(), re.MULTILINE | re.DOTALL)

    assert check_example(example, tmp_path) == []
    assert 'source "$NVM_DIR/nvm.sh"' in example
    assert "choices:" in example


def test_the_library_page_is_in_the_docs_nav():
    """The library page is listed in the site's navigation, under Documentation."""
    nav = (ROOT / "mkdocs.yml").read_text()

    assert "    - 📚 Your runbook library: library.md\n" in nav


def test_the_runbook_format_frontmatter_example_is_valid(tmp_path, without_shellcheck):
    """The frontmatter example uses every key, all valid, and its inputs only need using to make a clean runbook."""
    [frontmatter] = re.findall(
        r"^```yaml\n(---\n.*?---\n)```$", (DOCS / "runbook-format.md").read_text(), re.MULTILINE | re.DOTALL
    )
    body = '\n## Release\n\n```sh run\necho "<VERSION>" "$PUBLISH_TOKEN"\n```\n\n```python run\nprint("ok")\n```\n'

    findings = check_example(frontmatter + body, tmp_path)

    # The example sets python: uv run python, which is a real command wherever these tests run with uv.
    assert findings == []


def test_the_changelog_in_the_docs_matches_the_one_at_the_root():
    """docs/CHANGELOG.md is a copy of CHANGELOG.md, so the site always shows the real change log."""
    root = Path(__file__).parent.parent

    assert (root / "docs" / "CHANGELOG.md").read_text() == (root / "CHANGELOG.md").read_text()


def test_the_readme_example_runs_as_written(runner, tmp_path, monkeypatch, without_shellcheck):
    """The README's check-then-run commands, on the README's runbook, pass the check and run every step."""
    blocks = fences(ROOT / "README.md")
    [runbook] = [content for info, content in blocks if info == "markdown"]
    (tmp_path / "hello.md").write_text(runbook)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NAME", raising=False)
    [commands] = [content for info, content in blocks if info == "sh" and content.startswith("rundot ")]
    assert commands.splitlines() == ["rundot check hello.md", "rundot hello.md"]

    check, run = [runner.invoke(cli.cli, line.split()[1:], input="Paul\ny\n") for line in commands.splitlines()]

    assert check.exit_code == 0, check.output
    assert run.exit_code == 0, run.output
    assert "Hello, Paul!" in run.output
    assert "Paul has 4 letters" in run.output
    # A runbook runs in the folder you're in.
    assert "".join(overview(run.output)["directory"]) == str(tmp_path)


def test_the_backends_page_shows_the_real_backend_protocol():
    """Problem, the Backend protocol and stream() on the backends page are rundot's own, word for word."""
    code = [content for info, content in fences(DOCS / "backends.md") if info == "python"]

    assert any(inspect.getsource(Problem) in block for block in code)
    assert any(inspect.getsource(Backend) in block for block in code)
    stream_definition = inspect.getsource(backends.stream).splitlines()[0]
    assert any(stream_definition in block.splitlines() for block in code)


@pytest.fixture
def node_backend(tmp_path, monkeypatch):
    """The example backend from the backends page, installed the way its pyproject.toml registers it."""
    blocks = fences(DOCS / "backends.md")
    [pyproject] = [tomllib.loads(content) for info, content in blocks if info == "toml" and "[project]" in content]
    [(name, value)] = pyproject["project"]["entry-points"]["rundot.backends"].items()
    module, cls = value.split(":")
    [source] = [content for info, content in blocks if info == "python" and f"class {cls}:" in content]
    (tmp_path / f"{module}.py").write_text(source)
    monkeypatch.syspath_prepend(tmp_path)
    installed = list(backends.installed_entry_points())
    node = EntryPoint(name=name, value=value, group=backends.ENTRY_POINT_GROUP)
    monkeypatch.setattr(backends, "installed_entry_points", lambda: [*installed, node])
    yield
    sys.modules.pop(module, None)


@needs_node
def test_the_example_backend_runs_the_example_runbook(runner, node_backend, tmp_path):
    """The backends page's runbook runs its js block with the page's example backend."""
    [runbook] = [content for info, content in fences(DOCS / "backends.md") if info == "markdown"]
    path = tmp_path / "hello-node.md"
    path.write_text(runbook)

    result = runner.invoke(cli.cli, ["run", str(path)], input="y\n")

    assert result.exit_code == 0, result.output
    assert any(line.startswith("Hello from Node v") for line in printed(result.output)), result.output


@needs_node
def test_the_example_backend_finds_syntax_errors_on_the_right_line(runner, node_backend, tmp_path):
    """check reports a syntax error the example backend finds at its line in the runbook."""
    path = tmp_path / "runbook.md"
    path.write_text('---\ntitle: T\n---\n\n## Broken\n\n```js run\nconsole.log("ok");\nconst = 1;\n```\n')

    result = runner.invoke(cli.cli, ["check", str(path)])

    assert result.exit_code == 1
    assert f"{path}:9: error: SyntaxError: Unexpected token '='" in result.output.splitlines()


def test_the_input_block_examples_are_valid(tmp_path, without_shellcheck):
    """Each snippet in the format page's input blocks section passes check, inside the smallest runbook it needs."""
    page = (DOCS / "runbook-format.md").read_text()
    section = page[page.index("### Input blocks") : page.index("## Steps")]
    snippets = re.findall(r"^````markdown\n(.*?)^````$", section, re.MULTILINE | re.DOTALL)
    assert len(snippets) == 2

    for snippet in snippets:
        # Declare VERSION only for the snippet that uses it, so an unused input can't hide a real problem.
        inputs = "inputs:\n  - name: VERSION\n    description: The version\n" if "<VERSION>" in snippet else ""
        body = snippet if snippet.startswith("## ") else "## Publish\n\n" + snippet

        assert check_example(f"---\ntitle: T\n{inputs}---\n\n{body}", tmp_path) == [], snippet
