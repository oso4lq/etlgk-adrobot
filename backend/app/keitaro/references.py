from collections.abc import Sequence
from typing import Protocol


class _HasIdAndName(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def name(self) -> str: ...


def find_reference[T: _HasIdAndName](items: Sequence[T], configured: str) -> T | None:
    """Resolves a configured dictionary entry: digits mean id, anything else an exact name."""
    value = configured.strip()
    if value.isdecimal():
        wanted_id = int(value)
        for item in items:
            if item.id == wanted_id:
                return item
        return None
    for item in items:
        if item.name == value:
            return item
    return None
