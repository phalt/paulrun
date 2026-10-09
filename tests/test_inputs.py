"""Tests for collecting, substituting and masking input values."""

from dataclasses import dataclass, field

import pytest

from paulrun.inputs import Input, InputError, collect, mask, substitute

VERSION = Input(name="VERSION", description="The version", pattern=r"\d+\.\d+\.\d+")


@dataclass
class FakePrompter:
    """Gives the answers in order, recording each input it was asked for and the problem it was shown."""

    answers: list[str]
    asked: list[tuple[str, str | None]] = field(default_factory=list)

    def ask(self, input: Input, problem: str | None) -> str:
        self.asked.append((input.name, problem))
        return self.answers.pop(0)

    def confirm(self, question: str) -> str:
        raise AssertionError(f"collecting inputs shouldn't ask {question!r}")


def test_collect_uses_a_value_from_the_environment_without_prompting():
    """An input set in the environment is taken from there."""
    prompter = FakePrompter(answers=[])

    values = collect([VERSION], {"VERSION": "1.2.0"}, prompter)

    assert values == {"VERSION": "1.2.0"}
    assert prompter.asked == []


def test_collect_prompts_for_inputs_not_in_the_environment_in_order():
    """Inputs the environment doesn't set are asked for one at a time, in the order they're declared."""
    inputs = [Input(name="FIRST", description="First"), VERSION, Input(name="LAST", description="Last")]
    prompter = FakePrompter(answers=["one", "last"])

    values = collect(inputs, {"VERSION": "1.2.0"}, prompter)

    assert values == {"FIRST": "one", "VERSION": "1.2.0", "LAST": "last"}
    assert prompter.asked == [("FIRST", None), ("LAST", None)]


def test_collect_prompts_when_the_environment_value_is_empty():
    """An input set to an empty string in the environment counts as not set."""
    prompter = FakePrompter(answers=["1.2.0"])

    values = collect([VERSION], {"VERSION": ""}, prompter)

    assert values == {"VERSION": "1.2.0"}
    assert prompter.asked == [("VERSION", None)]


def test_collect_asks_again_when_an_answer_does_not_match_the_pattern():
    """A typed answer that doesn't match is refused, and the prompt says why."""
    prompter = FakePrompter(answers=["latest", "v1", "1.2.0"])

    values = collect([VERSION], {}, prompter)

    assert values == {"VERSION": "1.2.0"}
    assert prompter.asked == [
        ("VERSION", None),
        ("VERSION", r"VERSION must match \d+\.\d+\.\d+"),
        ("VERSION", r"VERSION must match \d+\.\d+\.\d+"),
    ]


def test_collect_needs_the_pattern_to_match_the_whole_value():
    """A pattern has to match all of the value, not just the start of it."""
    prompter = FakePrompter(answers=["1.2.0-rc1", "1.2.0"])

    values = collect([VERSION], {}, prompter)

    assert values == {"VERSION": "1.2.0"}
    assert len(prompter.asked) == 2


def test_collect_can_skip_secrets():
    """With skip_secrets, secrets are neither asked for nor read from the environment, and have no value."""
    inputs = [VERSION, Input(name="TOKEN", description="A token", pattern="t-.*", secret=True)]
    prompter = FakePrompter(answers=["1.2.0"])

    values = collect(inputs, {"TOKEN": "doesn't match"}, prompter, skip_secrets=True)

    assert values == {"VERSION": "1.2.0"}
    assert prompter.asked == [("VERSION", None)]


def test_collect_fails_when_an_environment_value_does_not_match_the_pattern():
    """A bad value from the environment can't be asked for again, so it's an error that doesn't show the value."""
    with pytest.raises(InputError) as error:
        collect([VERSION], {"VERSION": "latest"}, FakePrompter(answers=[]))

    assert str(error.value) == r"VERSION from the environment must match \d+\.\d+\.\d+"


def test_substitute_replaces_each_placeholder_with_its_value():
    """Every <NAME> that has a value is replaced, however many times it appears."""
    text = "git tag <VERSION> && echo <PACKAGE> <VERSION>"

    assert substitute(text, {"VERSION": "1.2.0", "PACKAGE": "paulrun"}) == "git tag 1.2.0 && echo paulrun 1.2.0"


def test_substitute_leaves_placeholders_without_a_value_alone():
    """A placeholder with no value, such as a secret's, stays exactly as written."""
    assert substitute("echo <VERSION> <TOKEN>", {"VERSION": "1.2.0"}) == "echo 1.2.0 <TOKEN>"


def test_substitute_puts_values_in_as_they_are():
    """A value that looks like a placeholder isn't substituted again."""
    assert substitute("<FIRST> <SECOND>", {"FIRST": "<SECOND>", "SECOND": "two"}) == "<SECOND> two"


def test_substitute_only_replaces_upper_snake_case_placeholders():
    """Text in angle brackets that isn't <[A-Z][A-Z0-9_]*> isn't a placeholder."""
    text = "<version> <1ST> < VERSION> <VERSION-2>"

    assert substitute(text, {"version": "x", "1ST": "x", "VERSION": "x"}) == text


def test_mask_replaces_every_occurrence_of_every_secret():
    """Each secret is replaced with **** everywhere it appears."""
    assert mask("token abc, key xyz, token abc again", ["abc", "xyz"]) == "token ****, key ****, token **** again"


def test_mask_hides_the_whole_of_a_secret_that_contains_another():
    """When one secret contains another, the longer one is masked whole, so none of it is left showing."""
    assert mask("key abcdef", ["abc", "abcdef"]) == "key ****"


def test_mask_matches_secrets_as_plain_text():
    """Characters that mean something in a regex only match themselves."""
    assert mask("p.s+w(rd but not pXss+w(rd", ["p.s+w(rd"]) == "**** but not pXss+w(rd"


def test_mask_ignores_empty_secrets():
    """An empty secret masks nothing, rather than matching between every character."""
    assert mask("plain text", [""]) == "plain text"


def test_mask_without_secrets_returns_text_unchanged():
    """With no secrets there is nothing to mask."""
    assert mask("plain text", []) == "plain text"
