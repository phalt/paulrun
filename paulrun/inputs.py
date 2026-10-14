import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

PLACEHOLDER = re.compile(r"<([A-Z][A-Z0-9_]*)>")

MASK = "****"


@dataclass(frozen=True)
class Input:
    name: str
    description: str
    pattern: str | None = None
    secret: bool = False
    default: str | None = None  # used for an empty answer at the prompt; never set for a secret
    choices: tuple[str, ...] = ()  # if any, the only values accepted; never set for a secret


class Prompter(Protocol):
    """Asks the person running the runbook for values and answers."""

    def ask(self, input: Input, problem: str | None) -> str:
        """Ask for an input's value, hiding what's typed if it's secret.

        problem is None the first time, then says why the previous answer was refused.
        """

    def confirm(self, question: str) -> str:
        """Ask a question, e.g. "Start? [y/N]", and return the answer as typed. Pressing enter gives ""."""


class InputError(Exception):
    """An input can't be collected, e.g. its value from the environment doesn't match its pattern."""


def collect(
    inputs: Iterable[Input], env: Mapping[str, str], prompter: Prompter, *, skip_secrets: bool = False
) -> dict[str, str]:
    """Get a value for each input, from env if it's set there, otherwise by asking until the answer is accepted.

    A value is accepted if it's one of the input's choices, if it has any, and matches its pattern. An empty
    answer to an input with a default is the default, which is checked like any answer. With skip_secrets,
    secrets are left out entirely: not read from env, not asked for, and not in the result.
    """
    values = {}
    for input in inputs:
        if skip_secrets and input.secret:
            continue
        # An empty variable counts as unset, so a stray `VERSION=` can't release an empty version.
        if value := env.get(input.name):
            if (problem := _problem(input, value)) is not None:
                raise InputError(f"{input.name} from the environment {problem}")
        else:
            value = _answer(input, prompter.ask(input, None))
            while (problem := _problem(input, value)) is not None:
                value = _answer(input, prompter.ask(input, f"{input.name} {problem}"))
        values[input.name] = value
    return values


def _answer(input: Input, answer: str) -> str:
    """The value an answer gives: the answer itself, or the input's default for an empty one."""
    return input.default if not answer and input.default is not None else answer


def _problem(input: Input, value: str) -> str | None:
    """Why value isn't accepted for input, e.g. "must match ^\\d+$", or None if it is."""
    if input.choices and value not in input.choices:
        return f"must be one of: {', '.join(input.choices)}"
    if input.pattern is not None and re.fullmatch(input.pattern, value) is None:
        return f"must match {input.pattern}"
    return None


def substitute(text: str, values: Mapping[str, str]) -> str:
    """Replace <NAME> placeholders with their values. Unknown names are left alone."""
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def mask(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of every secret with ****."""
    # Longest first, so a secret that contains another is masked whole rather than leaving its tail showing.
    ordered = sorted({secret for secret in secrets if secret}, key=len, reverse=True)
    if not ordered:
        return text
    return re.sub("|".join(re.escape(secret) for secret in ordered), MASK, text)
