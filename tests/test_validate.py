"""Tests for validating runbooks. Each error case has a broken fixture runbook in tests/runbooks/broken/."""

import shutil
import textwrap
from pathlib import Path

import pytest

from paulrun.backends import Problem, load_backends
from paulrun.runbook import parse
from paulrun.validate import Finding, Report, validate

RUNBOOKS = Path(__file__).parent / "runbooks"
BROKEN = RUNBOOKS / "broken"

# Each broken fixture, the file line of its one error, and the error's message.
BROKEN_CASES = [
    ("missing-title.md", 1, "title is required"),
    ("title-not-a-string.md", 2, "title must be a string"),
    ("input-missing-name.md", 4, "input 1 needs a name"),
    ("input-missing-description.md", 4, "input VERSION needs a description"),
    ("input-name-not-upper-snake-case.md", 4, "input name 'version' must be UPPER_SNAKE_CASE, e.g. VERSION"),
    (
        "invalid-pattern.md",
        4,
        "input VERSION's pattern isn't a valid regex: missing ), unterminated subpattern at position 1",
    ),
    ("undeclared-placeholder.md", 9, "<VERSION> isn't a declared input"),
    ("undeclared-placeholder-in-docstring.md", 8, "<VERSION> isn't a declared input"),
    ("undeclared-placeholder-in-confirm.md", 8, "<VERSION> isn't a declared input"),
    ("undeclared-placeholder-in-output-path.md", 3, "output_path: <VERSION> isn't a declared input"),
    (
        "secret-as-placeholder.md",
        12,
        "<TOKEN> is a secret, so it's never substituted; use $TOKEN to read it from the environment",
    ),
    ("run-block-with-no-backend.md", 7, "no backend runs 'cobol' blocks"),
    ("block-before-first-step.md", 7, "run blocks must be inside a step (a ## heading)"),
    ("python-not-on-path.md", 3, "python command 'paulrun-no-such-python' isn't on PATH"),
    ("shell-syntax-error.md", 10, "syntax error near unexpected token `fi'"),
    ("python-syntax-error.md", 9, "expected ':'"),
]

VALID_FIXTURES = [
    "all_features.md",
    "minimal.md",
    "two_steps.md",
    "inputs-example.md",
    "docstring-and-confirm-example.md",
    "dry-run-example.md",
    "python-example.md",
]


@pytest.fixture(autouse=True)
def path_without_shellcheck(monkeypatch, tmp_path_factory):
    """A PATH with only bash and python3 on it.

    shellcheck findings depend on which version is installed, so they're tested with a stub in the shell
    backend's tests. Here, validation gives the same result whether or not shellcheck is installed.
    """
    bin_dir = tmp_path_factory.mktemp("bin")
    for tool in ("bash", "python3"):
        found = shutil.which(tool)
        assert found is not None, f"{tool} is needed to run these tests"
        (bin_dir / tool).symlink_to(found)
    monkeypatch.setenv("PATH", str(bin_dir))


def write_runbook(tmp_path: Path, text: str) -> Path:
    """Write a dedented runbook into tmp_path and return its path."""
    path = tmp_path / "runbook.md"
    path.write_text(textwrap.dedent(text))
    return path


def check(path: Path) -> Report:
    """Validate the runbook at path against the installed backends."""
    return validate(parse(path), load_backends())


@pytest.mark.parametrize("fixture, line, message", BROKEN_CASES)
def test_validate_reports_each_broken_fixture(fixture, line, message):
    """Each broken fixture has exactly one error, with its message and the file line it's on, and no warnings."""
    report = check(BROKEN / fixture)

    assert report.findings == [Finding(line, message)]
    assert not report.ok


def test_every_broken_fixture_is_tested():
    """A broken fixture can't be added without a case asserting its error."""
    assert sorted(path.name for path in BROKEN.glob("*.md")) == sorted(case[0] for case in BROKEN_CASES)


@pytest.mark.parametrize("fixture", VALID_FIXTURES)
def test_validate_finds_no_problems_in_the_valid_fixtures(fixture):
    """The example runbooks are clean: no errors and no warnings."""
    report = check(RUNBOOKS / fixture)

    assert report.findings == []
    assert report.ok


def test_validate_warns_about_unknown_frontmatter_keys(tmp_path):
    """A top-level key paulrun doesn't know is a warning on its line, not an error."""
    path = write_runbook(tmp_path, "---\ntitle: Release\nversion: 2\n---\n\n## Only\n\n```sh run\ntrue\n```\n")

    report = check(path)

    assert report.findings == [Finding(3, "unknown frontmatter key 'version'", warning=True)]
    assert report.ok


def test_validate_warns_about_unknown_input_keys(tmp_path):
    """A key on an input that paulrun doesn't know is a warning on that input's line."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        inputs:
          - name: VERSION
            description: The version
            default: 1.0.0
        ---

        ## Only

        ```sh run
        echo <VERSION>
        ```
        """,
    )

    assert check(path).findings == [Finding(4, "unknown key 'default' on input VERSION", warning=True)]


def test_validate_warns_about_inputs_that_are_never_used(tmp_path):
    """An input no block uses, by placeholder or by name, is a warning."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        inputs:
          - name: VERSION
            description: The version
          - name: UNUSED
            description: Nothing reads this
        ---

        ## Only

        ```sh run
        echo <VERSION>
        ```
        """,
    )

    assert check(path).findings == [Finding(6, "input UNUSED is never used", warning=True)]


def test_validate_counts_an_input_read_from_the_environment_as_used(tmp_path):
    """A secret is only ever read as $NAME in a run block, and that counts as using it."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        inputs:
          - name: TOKEN
            description: A token
            secret: true
        ---

        ## Only

        ```sh run
        publish --token "$TOKEN"
        ```
        """,
    )

    assert check(path).findings == []


def test_validate_counts_a_placeholder_in_output_path_as_using_the_input(tmp_path):
    """An input only used in output_path is still used."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        output_path: logs/<VERSION>.md
        inputs:
          - name: VERSION
            description: The version
        ---

        ## Only

        ```sh run
        true
        ```
        """,
    )

    assert check(path).findings == []


def test_validate_reports_each_undeclared_placeholder_on_its_own_line(tmp_path):
    """Every undeclared placeholder is reported, on the file line it's written on."""
    path = write_runbook(tmp_path, "---\ntitle: T\n---\n\n## Only\n\n```sh run\necho <ONE>\n\necho <TWO> <ONE>\n```\n")

    assert check(path).errors == [
        Finding(8, "<ONE> isn't a declared input"),
        Finding(10, "<TWO> isn't a declared input"),
        Finding(10, "<ONE> isn't a declared input"),
    ]


def test_validate_reports_docstring_and_confirm_blocks_before_the_first_step(tmp_path):
    """Any kind of block before the first ## is an error, named by its kind."""
    path = write_runbook(tmp_path, "---\ntitle: T\n---\n\n```docstring\nhi\n```\n\n```confirm\nok?\n```\n\n## S\n")

    assert check(path).errors == [
        Finding(5, "docstring blocks must be inside a step (a ## heading)"),
        Finding(9, "confirm blocks must be inside a step (a ## heading)"),
    ]


def test_validate_ignores_fences_that_are_not_blocks(tmp_path):
    """Plain fences are documentation, so their contents are never checked."""
    path = write_runbook(tmp_path, "---\ntitle: T\n---\n\n```sh\nif <BROKEN>; then\n```\n\n## S\n")

    assert check(path).findings == []


@pytest.mark.parametrize(
    "frontmatter, line, message",
    [
        ("description: 3", 3, "description must be a string"),
        ("output_path: [a, b]", 3, "output_path must be a string"),
        ("python: 3.12", 3, "python must be a string"),
        ("inputs: VERSION", 3, "inputs must be a list"),
        ("inputs:\n  - VERSION", 4, "input 1 must be a mapping with a name and description"),
        ("inputs:\n  - name: 3\n    description: x", 4, "input 1 needs a name"),
        (
            "inputs:\n  - name: V\n    description: x\n    pattern: 3",
            4,
            "input V's pattern must be a string",
        ),
    ],
)
def test_validate_reports_frontmatter_values_of_the_wrong_type(tmp_path, frontmatter, line, message):
    """A core key with a value of the wrong type is an error on its line."""
    path = write_runbook(tmp_path, f"---\ntitle: T\n{frontmatter}\n---\n\n## S\n")

    assert Finding(line, message) in check(path).errors


@pytest.mark.parametrize(
    "name, suggestion",
    [("version", "VERSION"), ("publish-token", "PUBLISH_TOKEN"), ("2fa code", "INPUT_2FA_CODE"), ("---", "NAME")],
)
def test_validate_suggests_an_upper_snake_case_name(tmp_path, name, suggestion):
    """A badly formed input name is reported with a suggested UPPER_SNAKE_CASE version of it."""
    path = write_runbook(tmp_path, f"---\ntitle: T\ninputs:\n  - name: '{name}'\n    description: x\n---\n\n## S\n")

    assert Finding(4, f"input name {name!r} must be UPPER_SNAKE_CASE, e.g. {suggestion}") in check(path).errors


def test_validate_checks_python_only_when_the_runbook_has_python_blocks(tmp_path):
    """A python command that isn't installed doesn't matter if nothing uses it."""
    path = write_runbook(
        tmp_path, "---\ntitle: T\npython: paulrun-no-such-python\n---\n\n## S\n\n```sh run\ntrue\n```\n"
    )

    assert check(path).findings == []


def test_validate_accepts_a_python_command_on_path(tmp_path):
    """A python command whose first word is on PATH is fine, whatever its arguments."""
    path = write_runbook(tmp_path, "---\ntitle: T\npython: python3 -X dev\n---\n\n## S\n\n```py run\npass\n```\n")

    assert check(path).findings == []


def test_validate_reports_an_empty_python_command(tmp_path):
    """python: "" can't run anything."""
    path = write_runbook(tmp_path, "---\ntitle: T\npython: ''\n---\n\n## S\n\n```python run\npass\n```\n")

    assert check(path).errors == [Finding(3, "python command is empty")]


def test_validate_puts_block_wide_backend_problems_on_the_fence_line(tmp_path):
    """A backend problem with no line of its own is reported on the block's opening fence."""
    path = write_runbook(tmp_path, "---\ntitle: T\n---\n\n## S\n\n```fake run\nanything\n```\n")

    class WholeBlockBackend:
        name = "fake"
        languages = ("fake",)

        def validate(self, code):
            return [Problem("this whole block is wrong"), Problem("and this is a warning", line=1, warning=True)]

        def run(self, code, *, frontmatter, env, cwd, output):
            return 0

    report = validate(parse(path), {"fake": WholeBlockBackend()})

    assert report.findings == [
        Finding(7, "this whole block is wrong"),
        Finding(8, "and this is a warning", warning=True),
    ]


def test_report_lists_findings_in_line_order(tmp_path):
    """Findings from different checks are sorted by line, so the report reads top to bottom."""
    path = write_runbook(tmp_path, "---\nextra: 1\n---\n\n## S\n\n```sh run\necho <NOPE>\n```\n")

    assert [finding.line for finding in check(path).findings] == [1, 2, 8]


def test_report_separates_errors_from_warnings():
    """errors and warnings split the findings, and only errors make a report not ok."""
    report = Report([Finding(1, "an error"), Finding(2, "a warning", warning=True)])

    assert report.errors == [Finding(1, "an error")]
    assert report.warnings == [Finding(2, "a warning", warning=True)]
    assert not report.ok
    assert Report([Finding(2, "a warning", warning=True)]).ok


def test_report_sorts_findings_by_line_whichever_check_found_them(tmp_path):
    """A block problem above a frontmatter-only problem still comes first, so findings never jump around."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        inputs:
          - name: VERSION
            description: The version
        ---

        ```sh run
        echo before any step
        ```

        ## S

        ```sh run
        echo <NOPE>
        ```
        """,
    )

    # The unused input (line 4) is found after the placeholder check, the preamble block (line 8) after that.
    assert [finding.line for finding in check(path).findings] == [4, 8, 15]


def test_validate_suggests_only_names_that_are_themselves_valid():
    """Every suggestion is UPPER_SNAKE_CASE, even for a name that starts with a digit."""
    from paulrun.validate import _UPPER_SNAKE_CASE, _upper_snake

    for name in ["2fa", "9", "a-b", "Ünïcode", "_x_", "x1"]:
        assert _UPPER_SNAKE_CASE.fullmatch(_upper_snake(name)), name


def test_validate_reports_a_python_command_that_cannot_be_split(tmp_path):
    """An unclosed quote in the python command is an error, not a crash."""
    path = write_runbook(tmp_path, "---\ntitle: T\npython: '\"uv run'\n---\n\n## S\n\n```python run\npass\n```\n")

    assert check(path).errors == [Finding(3, "python command can't be read: No closing quotation")]
