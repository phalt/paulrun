"""Tests for runbook parsing."""

import textwrap
from pathlib import Path

import pytest

from paulrun import runbook
from paulrun.inputs import Input

RUNBOOKS = Path(__file__).parent / "runbooks"


def write_runbook(tmp_path: Path, text: str) -> Path:
    """Write a dedented runbook into tmp_path and return its path."""
    path = tmp_path / "runbook.md"
    path.write_text(textwrap.dedent(text))
    return path


def test_read_frontmatter_returns_yaml_mapping(tmp_path):
    """The YAML between the --- lines is returned as a mapping."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        description: Ship it.
        ---

        ## Step
        """,
    )

    assert runbook.read_frontmatter(path) == {"title": "Release", "description": "Ship it."}


def test_read_frontmatter_never_reads_past_closing_fence(tmp_path):
    """Nothing after the closing --- is decoded, so a body that would fail to parse doesn't matter."""
    path = tmp_path / "runbook.md"
    path.write_bytes(b"---\ntitle: Release\n---\n\n## Step\n\xff\xfe\n")
    with pytest.raises(UnicodeDecodeError):
        path.read_text(encoding="utf-8")  # guard: the body really is unreadable

    assert runbook.read_frontmatter(path) == {"title": "Release"}


def test_read_frontmatter_is_read_only(tmp_path):
    """Backends get the frontmatter, so it can't be changed through the mapping."""
    path = write_runbook(tmp_path, "---\ntitle: Release\n---\n")

    frontmatter = runbook.read_frontmatter(path)

    with pytest.raises(TypeError):
        frontmatter["title"] = "Changed"  # ty: ignore[invalid-assignment]


def test_read_frontmatter_without_frontmatter_is_empty(tmp_path):
    """A file that doesn't start with --- has no frontmatter."""
    path = write_runbook(tmp_path, "## Step\n")

    assert runbook.read_frontmatter(path) == {}


def test_read_frontmatter_with_empty_frontmatter_is_empty(tmp_path):
    """Nothing between the --- lines is an empty mapping, not an error."""
    path = write_runbook(tmp_path, "---\n---\n\n## Step\n")

    assert runbook.read_frontmatter(path) == {}


def test_read_frontmatter_rejects_unclosed_frontmatter(tmp_path):
    """An opening --- with no closing --- is an error."""
    path = write_runbook(tmp_path, "---\ntitle: Release\n\n## Step\n")

    with pytest.raises(runbook.RunbookError, match="no closing ---"):
        runbook.read_frontmatter(path)


def test_read_frontmatter_rejects_invalid_yaml_with_file_line(tmp_path):
    """YAML errors give the line in the file, not the line within the frontmatter."""
    path = write_runbook(tmp_path, "---\ntitle: Release\n  bad: indent\n---\n")

    with pytest.raises(runbook.RunbookError, match="line 3"):
        runbook.read_frontmatter(path)


def test_read_frontmatter_rejects_yaml_with_unreadable_characters(tmp_path):
    """Characters YAML refuses to read are an error too, even though YAML gives no line for them."""
    path = write_runbook(tmp_path, "---\ntitle: \x07\n---\n")

    with pytest.raises(runbook.RunbookError, match="frontmatter isn't valid YAML"):
        runbook.read_frontmatter(path)


def test_read_frontmatter_rejects_yaml_that_is_not_a_mapping(tmp_path):
    """Frontmatter has to be a mapping of keys to values."""
    path = write_runbook(tmp_path, "---\n- title\n- Release\n---\n")

    with pytest.raises(runbook.RunbookError, match="must be a YAML mapping"):
        runbook.read_frontmatter(path)


def test_read_frontmatter_reports_line_that_is_not_utf8(tmp_path):
    """Bytes that aren't UTF-8 in the frontmatter are an error naming the line."""
    path = tmp_path / "runbook.md"
    path.write_bytes(b"---\ntitle: \xff\n---\n")

    with pytest.raises(runbook.RunbookError, match="line 2 isn't valid UTF-8"):
        runbook.read_frontmatter(path)


def test_parse_names_steps_after_h2_headings(tmp_path):
    """Each ## heading starts a step named after the heading text."""
    path = write_runbook(
        tmp_path,
        """\
        ## Bump the version

        ## Publish it ##
        """,
    )

    parsed = runbook.parse(path)

    assert [step.name for step in parsed.steps] == ["Bump the version", "Publish it"]


def test_parse_keeps_steps_with_no_blocks(tmp_path):
    """A step that's only prose is still a step."""
    path = write_runbook(tmp_path, "## Read this\n\nJust prose.\n")

    parsed = runbook.parse(path)

    assert parsed.steps == (runbook.Step(name="Read this", line=1, blocks=()),)


def test_parse_reads_docstring_confirm_and_run_blocks(tmp_path):
    """The fence info string decides the block kind; run blocks keep their language."""
    path = write_runbook(
        tmp_path,
        """\
        ## Release

        ```docstring
        About to release.
        ```

        ```confirm
        Edit the changelog.
        ```

        ```sh run
        make release
        ```
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.steps[0].blocks == (
        runbook.Block(kind="docstring", language=None, content="About to release.\n", line=3),
        runbook.Block(kind="confirm", language=None, content="Edit the changelog.\n", line=7),
        runbook.Block(kind="run", language="sh", content="make release\n", line=11),
    )


def test_parse_ignores_fences_not_marked_run(tmp_path):
    """Plain fences are documentation, including ones in a language that has a backend."""
    path = write_runbook(
        tmp_path,
        """\
        ## Release

        ```sh
        make release
        ```

        ```toml
        version = "1.0.0"
        ```

        ```python
        print("hello")
        ```

        ```
        no info string
        ```

        ```run
        run is a language here, not a marker
        ```

            indented code
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.steps[0].blocks == ()


def test_parse_ignores_whitespace_and_words_after_run(tmp_path):
    """Only the first two words of the info string matter."""
    path = write_runbook(
        tmp_path,
        """\
        ## Release

        ```   bash   run   extra words
        make release
        ```
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.steps[0].blocks == (runbook.Block(kind="run", language="bash", content="make release\n", line=3),)


def test_parse_docstring_and_confirm_are_never_run_blocks(tmp_path):
    """A docstring or confirm fence with run after it is still only printed, never executed."""
    path = write_runbook(
        tmp_path,
        """\
        ## Release

        ```docstring run
        Printed.
        ```

        ```confirm run
        Confirmed.
        ```
        """,
    )

    parsed = runbook.parse(path)

    assert [block.kind for block in parsed.steps[0].blocks] == ["docstring", "confirm"]


def test_parse_finds_blocks_inside_lists(tmp_path):
    """Fences nested in a list item are blocks, with the list indentation removed."""
    path = write_runbook(
        tmp_path,
        """\
        ## Release

        1. Build it:

           ```sh run
           make build
           ```
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.steps[0].blocks == (runbook.Block(kind="run", language="sh", content="make build\n", line=5),)


def test_parse_treats_deeper_headings_as_prose(tmp_path):
    """### and deeper stay inside the current step."""
    path = write_runbook(
        tmp_path,
        """\
        ## Release

        ### Build

        ```sh run
        make build
        ```

        #### Publish

        ```sh run
        make publish
        ```
        """,
    )

    parsed = runbook.parse(path)

    assert [step.name for step in parsed.steps] == ["Release"]
    assert [block.content for block in parsed.steps[0].blocks] == ["make build\n", "make publish\n"]


def test_parse_ignores_headings_inside_fences(tmp_path):
    """A ## line inside a fence is code, not a step."""
    path = write_runbook(
        tmp_path,
        """\
        ## Release

        ```sh run
        cat <<EOF
        ## Not a step
        EOF
        ```
        """,
    )

    parsed = runbook.parse(path)

    assert [step.name for step in parsed.steps] == ["Release"]


def test_parse_treats_setext_h2_as_a_step(tmp_path):
    """An underlined heading renders as an h2, so it starts a step like ## does."""
    path = write_runbook(
        tmp_path,
        """\
        Release
        -------

        ```sh run
        make release
        ```
        """,
    )

    parsed = runbook.parse(path)

    assert [step.name for step in parsed.steps] == ["Release"]
    assert len(parsed.steps[0].blocks) == 1


def test_parse_keeps_blocks_before_first_step_in_preamble(tmp_path):
    """Blocks before the first ## aren't in any step; validation reports them later."""
    path = write_runbook(
        tmp_path,
        """\
        # Releasing

        ```sh
        documentation, ignored
        ```

        ```sh run
        make release
        ```

        ## Release
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.preamble == (runbook.Block(kind="run", language="sh", content="make release\n", line=7),)
    assert parsed.steps == (runbook.Step(name="Release", line=11, blocks=()),)


def test_parse_counts_lines_from_top_of_file(tmp_path):
    """Step and block line numbers point at the file, frontmatter included."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        ---

        ## Release

        ```sh run
        make release
        ```
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.steps[0].line == 5
    assert parsed.steps[0].blocks[0].line == 7


def test_parse_does_not_mistake_frontmatter_for_a_heading(tmp_path):
    """The closing --- would underline the YAML as a heading if the body parser saw it."""
    path = write_runbook(tmp_path, "---\ntitle: Release\n---\n")

    parsed = runbook.parse(path)

    assert parsed.frontmatter == {"title": "Release"}
    assert parsed.steps == ()


def test_parse_reports_body_line_that_is_not_utf8(tmp_path):
    """Bytes that aren't UTF-8 in the body are an error naming the line in the file."""
    path = tmp_path / "runbook.md"
    path.write_bytes(b"---\ntitle: Release\n---\n\n## Step\n\xff\xfe\n")

    with pytest.raises(runbook.RunbookError, match="line 6 isn't valid UTF-8"):
        runbook.parse(path)


def test_parse_all_features_fixture_into_steps_and_blocks():
    """The fixture using every part of the format parses into the expected steps and blocks."""
    parsed = runbook.parse(RUNBOOKS / "all_features.md")

    assert parsed.preamble == ()
    assert parsed.steps == (
        runbook.Step(
            name="Check the version",
            line=24,
            blocks=(
                runbook.Block(kind="docstring", language=None, content="Releasing <VERSION>.\n", line=26),
                runbook.Block(kind="run", language="sh", content='echo "Releasing <VERSION>"\n', line=30),
            ),
        ),
        runbook.Step(
            name="Update the version",
            line=38,
            blocks=(
                runbook.Block(
                    kind="confirm",
                    language=None,
                    content='Set version = "<VERSION>" in pyproject.toml and save it.\n',
                    line=46,
                ),
                runbook.Block(kind="run", language="python", content='print("Version <VERSION> set")\n', line=50),
            ),
        ),
        runbook.Step(
            name="Build and publish",
            line=54,
            blocks=(
                runbook.Block(kind="run", language="bash", content='echo "Building <VERSION>"\n', line=58),
                runbook.Block(
                    kind="run",
                    language="shell",
                    content='echo "Publishing with a ${#PUBLISH_TOKEN} character token"\n',
                    line=64,
                ),
            ),
        ),
    )


def test_parse_all_features_fixture_core_keys():
    """Core frontmatter keys are read into the model."""
    parsed = runbook.parse(RUNBOOKS / "all_features.md")

    assert parsed.title == "Release example"
    assert parsed.description == "A runbook that uses every part of the format."
    assert parsed.output_path == "logs/release-<VERSION>.md"
    assert parsed.python == "python3"


def test_parse_all_features_fixture_inputs():
    """Declared inputs are read in order, with their optional pattern and secret flag."""
    parsed = runbook.parse(RUNBOOKS / "all_features.md")

    assert parsed.inputs == (
        Input(name="VERSION", description="The version being released, e.g. 1.2.0", pattern=r"^\d+\.\d+\.\d+$"),
        Input(name="PUBLISH_TOKEN", description="Token for the package index", secret=True),
    )


def test_parse_minimal_fixture():
    """The smallest valid runbook: a title, one step and one run block."""
    parsed = runbook.parse(RUNBOOKS / "minimal.md")

    assert parsed.title == "Minimal"
    assert parsed.inputs == ()
    assert parsed.steps == (
        runbook.Step(
            name="Say hello",
            line=5,
            blocks=(runbook.Block(kind="run", language="sh", content="echo hello\n", line=7),),
        ),
    )


def test_parse_without_frontmatter_has_no_core_keys(tmp_path):
    """Missing keys are None rather than errors; validation reports a missing title."""
    path = write_runbook(tmp_path, "## Step\n")

    parsed = runbook.parse(path)

    assert (parsed.title, parsed.description, parsed.output_path, parsed.python) == (None, None, None, None)
    assert parsed.inputs == ()


def test_parse_core_key_that_is_not_a_string_is_none(tmp_path):
    """A core key with the wrong type is left for validation, but kept in the raw frontmatter."""
    path = write_runbook(tmp_path, "---\ntitle: [Release, it]\n---\n")

    parsed = runbook.parse(path)

    assert parsed.title is None
    assert parsed.frontmatter["title"] == ["Release", "it"]


def test_parse_skips_malformed_inputs(tmp_path):
    """Inputs without a string name and description are left out; validation reports them from the frontmatter."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        title: Release
        inputs:
          - VERSION
          - description: No name
          - name: NO_DESCRIPTION
          - name: 42
            description: Name isn't a string
          - name: GOOD
            description: Kept
        ---
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.inputs == (Input(name="GOOD", description="Kept"),)
    assert len(parsed.frontmatter["inputs"]) == 5


def test_parse_inputs_that_are_not_a_list_are_empty(tmp_path):
    """inputs has to be a list of mappings; anything else gives no inputs."""
    path = write_runbook(tmp_path, "---\ntitle: Release\ninputs: VERSION\n---\n")

    parsed = runbook.parse(path)

    assert parsed.inputs == ()


def test_parse_pattern_that_is_not_a_string_is_none(tmp_path):
    """A pattern with the wrong type is dropped rather than turned into a string."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        inputs:
          - name: VERSION
            description: Version
            pattern: [1, 2]
        ---
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.inputs == (Input(name="VERSION", description="Version"),)


def test_parse_secret_that_is_not_a_bool_is_still_secret(tmp_path):
    """Anything truthy marks an input secret, so a typo can only hide a value, never leak it."""
    path = write_runbook(
        tmp_path,
        """\
        ---
        inputs:
          - name: TOKEN
            description: Token
            secret: "false"
        ---
        """,
    )

    parsed = runbook.parse(path)

    assert parsed.inputs[0].secret is True
