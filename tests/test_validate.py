"""Tests for validating runbooks. Each error case has a broken fixture runbook in tests/runbooks/broken/."""

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
    ("duplicate-input-name.md", 6, "input VERSION is declared twice (first on line 4)"),
    ("input-block-invalid-yaml.md", 9, "input block isn't valid YAML: expected ',' or ']', but got ':'"),
    ("input-block-not-a-mapping.md", 7, "input block must be a mapping with a name and description"),
    ("input-block-missing-description.md", 7, "input OTP needs a description"),
    ("input-block-name-already-declared.md", 10, "input OTP is declared twice (first on line 4)"),
    ("input-block-placeholder-used-before.md", 8, "<PR> is used before its input block on line 13"),
    ("input-block-env-used-before.md", 8, "$PR is used before its input block on line 13"),
    (
        "input-block-in-output-path.md",
        3,
        "output_path: <PR> comes from an input block, so it isn't known when the run starts",
    ),
    ("input-block-before-first-step.md", 5, "input blocks must be inside a step (a ## heading)"),
    ("title-not-a-string.md", 2, "title must be a string"),
    ("step-not-true-or-false.md", 3, "step must be true or false"),
    ("input-missing-name.md", 4, "input 1 needs a name"),
    ("input-missing-description.md", 4, "input VERSION needs a description"),
    ("input-name-not-upper-snake-case.md", 4, "input name 'version' must be UPPER_SNAKE_CASE, e.g. VERSION"),
    (
        "default-not-a-string.md",
        4,
        "input VERSION's default must be a string, but YAML read it as the number 1.1; put it in quotes",
    ),
    (
        "default-on-a-secret.md",
        4,
        "input TOKEN is secret, so it can't have a default: its value would be written in the runbook",
    ),
    ("default-does-not-match-pattern.md", 4, "input VERSION's default 'latest' doesn't match its pattern"),
    ("choices-not-a-list-of-strings.md", 4, "input FE_SET's choices must be a list of strings, e.g. [a, b]"),
    (
        "choices-on-a-secret.md",
        4,
        "input TOKEN is secret, so it can't have choices: its values would be written in the runbook",
    ),
    ("choice-does-not-match-pattern.md", 4, "input ENV's choice 'prod-eu' doesn't match its pattern"),
    ("default-not-one-of-the-choices.md", 4, "input FE_SET's default 'everything' isn't one of its choices"),
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
    "step-example.md",
    "step-frontmatter-example.md",
    "transcript-example.md",
    "input-block-example.md",
    "default-example.md",
    "choices-example.md",
]


@pytest.fixture(autouse=True)
def shellcheck_not_installed(without_shellcheck):
    """Output is the same whether or not shellcheck is installed. See without_shellcheck in conftest.py."""


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
            example: 1.0.0
        ---

        ## Only

        ```sh run
        echo <VERSION>
        ```
        """,
    )

    assert check(path).findings == [Finding(4, "unknown key 'example' on input VERSION", warning=True)]


def test_validate_accepts_a_string_default_that_matches_the_pattern(tmp_path):
    """default is a known key, and a quoted default that matches the whole pattern is fine."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        inputs:
          - name: VERSION
            description: The version
            pattern: '^\\d+\\.\\d+\\.\\d+$'
            default: '1.10.0'
        ---

        ## Only

        ```sh run
        echo <VERSION>
        ```
        """,
    )

    assert check(path).findings == []


def test_validate_checks_a_default_against_the_whole_pattern(tmp_path):
    """A pattern has to match all of the default, the same as for a typed answer."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        inputs:
          - name: VERSION
            description: The version
            pattern: '\\d+'
            default: 12abc
        ---

        ## Only

        ```sh run
        echo <VERSION>
        ```
        """,
    )

    assert check(path).errors == [Finding(4, "input VERSION's default '12abc' doesn't match its pattern")]


def test_validate_only_reports_the_pattern_when_it_is_broken_not_the_default_too(tmp_path):
    """A default can't be checked against a pattern that isn't a valid regex, so only the pattern is reported."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        inputs:
          - name: VERSION
            description: The version
            pattern: '^(\\d+$'
            default: '1'
        ---

        ## Only

        ```sh run
        echo <VERSION>
        ```
        """,
    )

    [error] = check(path).errors
    assert error.message.startswith("input VERSION's pattern isn't a valid regex")


@pytest.mark.parametrize(
    ("written", "read_as"),
    [
        ("yes", "true, a yes or no"),
        ("3", "the number 3"),
        ("2026-10-14", "a date, 2026-10-14"),
        ("[main, release]", "a list"),
        ("", "nothing"),
    ],
)
def test_validate_says_what_yaml_made_of_a_default_that_is_not_a_string(written, read_as, tmp_path):
    """Unquoted YAML isn't always text, so the error says what it became, to make the fix obvious."""
    path = write_runbook(
        tmp_path,
        f"---\ntitle: T\ninputs:\n  - name: BRANCH\n    description: B\n    default: {written}\n---\n\n"
        "## Only\n\n```sh run\necho <BRANCH>\n```\n",
    )

    assert check(path).errors == [
        Finding(4, f"input BRANCH's default must be a string, but YAML read it as {read_as}; put it in quotes")
    ]


def choices_runbook(tmp_path: Path, keys: str, block: str = 'echo "<FE_SET>"') -> Path:
    """A runbook with one input, FE_SET, on line 4, with keys added to it."""
    return write_runbook(
        tmp_path,
        f"---\ntitle: T\ninputs:\n  - name: FE_SET\n    description: Which set\n{keys}---\n\n"
        f"## Only\n\n```sh run\n{block}\n```\n",
    )


def test_validate_accepts_choices_with_a_default_among_them(tmp_path):
    """choices is a known key, and a list of strings with a default that's one of them is fine."""
    path = choices_runbook(tmp_path, "    choices: [comms, billing, all]\n    default: comms\n")

    assert check(path).findings == []


@pytest.mark.parametrize("choices", ["comms", "[]", "[comms, 3]", "{a: b}", "''"])
def test_validate_reports_choices_that_are_not_a_non_empty_list_of_strings(choices, tmp_path):
    """Choices have to be a list, with at least one choice, and every choice text."""
    path = choices_runbook(tmp_path, f"    choices: {choices}\n")

    assert check(path).errors == [Finding(4, "input FE_SET's choices must be a list of strings, e.g. [a, b]")]


def test_validate_reports_every_choice_the_pattern_refuses(tmp_path):
    """Each choice that could never be accepted is its own error."""
    path = choices_runbook(tmp_path, "    pattern: '^[a-z]+$'\n    choices: [comms, bill-ing, ALL]\n")

    assert check(path).errors == [
        Finding(4, "input FE_SET's choice 'bill-ing' doesn't match its pattern"),
        Finding(4, "input FE_SET's choice 'ALL' doesn't match its pattern"),
    ]


def test_validate_only_reports_a_broken_pattern_not_the_choices_too(tmp_path):
    """Choices can't be checked against a pattern that isn't a valid regex, so only the pattern is reported."""
    path = choices_runbook(tmp_path, "    pattern: '^(a$'\n    choices: [comms]\n")

    [error] = check(path).errors
    assert error.message.startswith("input FE_SET's pattern isn't a valid regex")


def test_validate_reports_a_default_outside_the_choices_once_even_if_the_pattern_refuses_it_too(tmp_path):
    """A default that's neither a choice nor matches the pattern is one problem, named by the choices."""
    path = choices_runbook(tmp_path, "    pattern: '^[a-z]+$'\n    choices: [comms]\n    default: ALL\n")

    assert check(path).errors == [Finding(4, "input FE_SET's default 'ALL' isn't one of its choices")]


def test_validate_does_not_check_a_default_against_choices_that_are_not_usable(tmp_path):
    """With choices of the wrong shape, only the choices are reported, not the default against them."""
    path = choices_runbook(tmp_path, "    choices: comms\n    default: billing\n")

    assert check(path).errors == [Finding(4, "input FE_SET's choices must be a list of strings, e.g. [a, b]")]


def test_validate_applies_the_choices_rules_to_input_blocks(tmp_path):
    """An input block's choices are checked the same way as a frontmatter input's."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        ---

        ## Deploy

        ```input
        name: ENV
        description: Where to deploy
        choices: [staging, prod]
        default: dev
        ```

        ```sh run
        echo <ENV>
        ```
        """,
    )

    assert check(path).errors == [Finding(7, "input ENV's default 'dev' isn't one of its choices")]


def test_validate_applies_the_default_rules_to_input_blocks(tmp_path):
    """An input block's default is checked the same way as a frontmatter input's."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        ---

        ## Open the pull request

        ```input
        name: PR
        description: The pull request number
        pattern: '\\d+'
        default: latest
        ```

        ```sh run
        echo <PR>
        ```
        """,
    )

    assert check(path).errors == [Finding(7, "input PR's default 'latest' doesn't match its pattern")]


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


def test_validate_treats_paulrun_runbook_dir_as_an_environment_variable_not_an_input(tmp_path):
    """PAULRUN_RUNBOOK_DIR is set for every block but isn't an input, so it's read as $PAULRUN_RUNBOOK_DIR only."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        ---

        ## Only

        ```sh run
        cat "$PAULRUN_RUNBOOK_DIR/notes.md"
        echo <PAULRUN_RUNBOOK_DIR>
        ```
        """,
    )

    assert check(path).errors == [Finding(9, "<PAULRUN_RUNBOOK_DIR> isn't a declared input")]


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
        ("step: 1", 3, "step must be true or false"),
        ("step: 'true'", 3, "step must be true or false"),
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


def test_validate_reports_every_repeat_of_an_input_name(tmp_path):
    """Each extra declaration of a name is an error on its own line, pointing back to the first."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        inputs:
          - name: TOKEN
            description: First
          - name: TOKEN
            description: Second
            secret: true
          - name: TOKEN
            description: Third
        ---

        ## S

        ```sh run
        echo "$TOKEN"
        ```
        """,
    )

    assert check(path).errors == [
        Finding(6, "input TOKEN is declared twice (first on line 4)"),
        Finding(9, "input TOKEN is declared twice (first on line 4)"),
    ]


def test_validate_judges_a_repeated_input_by_its_first_declaration(tmp_path):
    """Other checks treat the first declaration as the input, so the repeat only gets its own error."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        inputs:
          - name: TOKEN
            description: The first one, which isn't secret
          - name: TOKEN
            description: A repeat that says it is
            secret: true
          - name: UNUSED
            description: Never used
          - name: UNUSED
            description: Repeated
        ---

        ## S

        ```sh run
        echo <TOKEN>
        ```
        """,
    )

    assert check(path).findings == [
        Finding(6, "input TOKEN is declared twice (first on line 4)"),
        Finding(9, "input UNUSED is never used", warning=True),
        Finding(11, "input UNUSED is declared twice (first on line 9)"),
    ]


def test_validate_accepts_an_input_block_used_after_it(tmp_path):
    """Using an input block's value after the block, as a placeholder or from the environment, is fine."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        ---

        ## Open the pull request

        ```confirm
        Open a pull request.
        ```

        ```input
        name: PR
        description: The <PR> number GitHub gave the pull request
        ```

        ```sh run
        echo "merging <PR>"
        gh pr merge "$PR"
        ```

        ## Announce

        ```docstring
        Announcing PR <PR>.
        ```
        """,
    )

    assert check(path).findings == []


def test_validate_warns_about_an_input_block_that_is_never_used(tmp_path):
    """An input block nothing uses gets the same warning as an unused frontmatter input."""
    path = write_runbook(tmp_path, "---\ntitle: T\n---\n\n## S\n\n```input\nname: PR\ndescription: x\n```\n")

    assert check(path).findings == [Finding(7, "input PR is never used", warning=True)]


def test_validate_rejects_a_secret_input_block_used_as_a_placeholder(tmp_path):
    """A secret from an input block is never substituted, the same as a secret from the frontmatter."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        ---

        ## S

        ```input
        name: OTP
        description: x
        secret: true
        ```

        ```sh run
        npm publish --otp <OTP>
        ```
        """,
    )

    assert check(path).errors == [
        Finding(14, "<OTP> is a secret, so it's never substituted; use $OTP to read it from the environment")
    ]


def test_validate_reports_two_input_blocks_with_one_name(tmp_path):
    """Two input blocks can't declare the same name either."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        ---

        ## S

        ```input
        name: PR
        description: x
        ```

        ```input
        name: PR
        description: y
        ```

        ```sh run
        echo <PR>
        ```
        """,
    )

    assert check(path).errors == [Finding(12, "input PR is declared twice (first on line 7)")]


def test_validate_applies_frontmatter_input_rules_to_input_blocks(tmp_path):
    """Bad names, bad patterns and unknown keys are reported on an input block's fence line."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        ---

        ## S

        ```input
        name: pr
        description: x
        pattern: '['
        example: 1
        ```

        ```sh run
        echo $pr
        ```
        """,
    )

    assert [finding.message for finding in check(path).findings] == [
        "input name 'pr' must be UPPER_SNAKE_CASE, e.g. PR",
        "input pr's pattern isn't a valid regex: unterminated character set at position 0",
        "unknown key 'example' on input pr",
    ]
    assert {finding.line for finding in check(path).findings} == {7}


def test_validate_reports_an_input_block_with_no_name(tmp_path):
    """An input block without a name is named by what it is."""
    path = write_runbook(tmp_path, "---\ntitle: T\n---\n\n## S\n\n```input\ndescription: x\n```\n")

    assert check(path).errors == [Finding(7, "input block needs a name")]


def test_validate_reports_an_empty_input_block(tmp_path):
    """An empty input block declares nothing, which is an error."""
    path = write_runbook(tmp_path, "---\ntitle: T\n---\n\n## S\n\n```input\n```\n")

    assert check(path).errors == [Finding(7, "input block must be a mapping with a name and description")]


def test_validate_does_not_read_an_input_blocks_own_text_as_placeholders(tmp_path):
    """An input block's YAML declares an input; it isn't text paulrun fills in, so <NAME> in it is just text."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: T
        ---

        ## S

        ```input
        name: OTP
        description: Your <OTP> code, or <ANY> other text
        secret: true
        ```

        ```sh run
        npm publish --otp "$OTP"
        ```
        """,
    )

    assert check(path).findings == []
