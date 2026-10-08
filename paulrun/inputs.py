import re
from dataclasses import dataclass

PLACEHOLDER = re.compile(r"<([A-Z][A-Z0-9_]*)>")


@dataclass(frozen=True)
class Input:
    name: str
    description: str
    pattern: str | None = None
    secret: bool = False
