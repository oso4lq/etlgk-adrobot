"""A user-facing message about the state of a stream (problem blocks Push, warning does not)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Notice:
    code: str
    message: str
