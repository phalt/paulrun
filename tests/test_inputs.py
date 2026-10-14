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


def test_collect_takes_the_default_when_the_answer_is_empty():
    """Pressing enter at a prompt for an input with a default gives the default."""
    branch = Input(name="BRANCH", description="The branch", default="main")
    prompter = FakePrompter(answers=[""])

    values = collect([branch], {}, prompter)

    assert values == {"BRANCH": "main"}
    assert prompter.asked == [("BRANCH", None)]


def test_collect_uses_a_typed_answer_over_the_default():
    """The default is only for an empty answer; anything typed is used as it is."""
    branch = Input(name="BRANCH", description="The branch", default="main")

    assert collect([branch], {}, FakePrompter(answers=["release"])) == {"BRANCH": "release"}


def test_collect_uses_the_environment_over_the_default_without_asking():
    """The environment still comes first, so BRANCH=release overrides the default and nothing is asked."""
    branch = Input(name="BRANCH", description="The branch", default="main")
    prompter = FakePrompter(answers=[])

    assert collect([branch], {"BRANCH": "release"}, prompter) == {"BRANCH": "release"}
    assert prompter.asked == []


def test_collect_still_asks_for_an_input_with_a_default():
    """A default is offered at the prompt, not used silently, so the person running it can see and change it."""
    branch = Input(name="BRANCH", description="The branch", default="main")
    prompter = FakePrompter(answers=[""])

    collect([branch], {}, prompter)

    assert prompter.asked == [("BRANCH", None)]


def test_collect_keeps_an_empty_answer_when_there_is_no_default():
    """Without a default, an empty answer is still the empty string, as before."""
    note = Input(name="NOTE", description="A note")

    assert collect([note], {}, FakePrompter(answers=[""])) == {"NOTE": ""}


def test_collect_checks_a_default_against_the_pattern():
    """A default is checked like any answer, so a default that doesn't match is refused and asked for again.

    check reports such a default before a run starts, so this only matters for a runbook run without checking.
    """
    version = Input(name="VERSION", description="The version", pattern=r"\d+\.\d+\.\d+", default="latest")
    prompter = FakePrompter(answers=["", "1.2.0"])

    assert collect([version], {}, prompter) == {"VERSION": "1.2.0"}
    assert prompter.asked == [("VERSION", None), ("VERSION", r"VERSION must match \d+\.\d+\.\d+")]


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


FE_SET = Input(name="FE_SET", description="Which set", choices=("comms", "billing", "all"))


def test_collect_accepts_an_answer_that_is_one_of_the_choices():
    """A typed answer that's one of the choices is used."""
    assert collect([FE_SET], {}, FakePrompter(answers=["billing"])) == {"FE_SET": "billing"}


def test_collect_asks_again_when_an_answer_is_not_one_of_the_choices():
    """An answer that isn't one of the choices is refused, and the prompt lists them."""
    prompter = FakePrompter(answers=["everything", "Comms", "comms"])

    values = collect([FE_SET], {}, prompter)

    assert values == {"FE_SET": "comms"}
    assert prompter.asked == [
        ("FE_SET", None),
        ("FE_SET", "FE_SET must be one of: comms, billing, all"),
        ("FE_SET", "FE_SET must be one of: comms, billing, all"),
    ]


def test_collect_fails_when_an_environment_value_is_not_one_of_the_choices():
    """A value from the environment can't be asked for again, so one outside the choices is an error."""
    with pytest.raises(InputError) as error:
        collect([FE_SET], {"FE_SET": "everything"}, FakePrompter(answers=[]))

    assert str(error.value) == "FE_SET from the environment must be one of: comms, billing, all"


def test_collect_takes_a_default_that_is_one_of_the_choices():
    """Pressing enter gives the default, which is one of the choices."""
    with_default = Input(name="FE_SET", description="Which set", choices=("comms", "billing"), default="comms")

    assert collect([with_default], {}, FakePrompter(answers=[""])) == {"FE_SET": "comms"}


def test_collect_needs_a_value_to_pass_both_choices_and_pattern():
    """With both set, a choice the pattern refuses is refused too, and the message names the choices."""
    both = Input(name="ENV", description="Where", choices=("staging", "prod"), pattern="staging")
    prompter = FakePrompter(answers=["prod", "staging"])

    assert collect([both], {}, prompter) == {"ENV": "staging"}
    assert prompter.asked == [("ENV", None), ("ENV", "ENV must match staging")]


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
