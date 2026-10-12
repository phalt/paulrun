"""Tests that the examples in the docs are real, valid runbooks, so the docs can't drift from the format."""

import re
from pathlib import Path

from paulrun.backends import load_backends
from paulrun.runbook import parse
from paulrun.validate import validate

DOCS = Path(__file__).parent.parent / "docs"


def check_example(text: str, tmp_path: Path) -> list[str]:
    """Write a runbook from the docs to a file and return everything check finds in it."""
    path = tmp_path / "RELEASING.md"
    path.write_text(text)
    return [f"{finding.line}: {finding.message}" for finding in validate(parse(path), load_backends()).findings]


def test_the_home_page_example_runbook_is_valid(tmp_path, without_shellcheck):
    """The runbook on the home page passes check with no errors or warnings."""
    [example] = re.findall(r"^````markdown\n(.*?)^````$", (DOCS / "index.md").read_text(), re.MULTILINE | re.DOTALL)

    assert check_example(example, tmp_path) == []


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
