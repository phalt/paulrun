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
    """Get a value for each input, from env if it's set there, otherwise by asking until the answer matches.

    With skip_secrets, secrets are left out entirely: not read from env, not asked for, and not in the result.
    """
    values = {}
    for input in inputs:
        if skip_secrets and input.secret:
            continue
        # An empty variable counts as unset, so a stray `VERSION=` can't release an empty version.
        if value := env.get(input.name):
            if not _matches(input, value):
                raise InputError(f"{input.name} from the environment must match {input.pattern}")
        else:
            value = prompter.ask(input, None)
            while not _matches(input, value):
                value = prompter.ask(input, f"{input.name} must match {input.pattern}")
        values[input.name] = value
    return values


def _matches(input: Input, value: str) -> bool:
    return input.pattern is None or re.fullmatch(input.pattern, value) is not None


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
