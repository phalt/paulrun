from dataclasses import dataclass


@dataclass(frozen=True)
class Input:
    name: str
    description: str
    pattern: str | None = None
    secret: bool = False
