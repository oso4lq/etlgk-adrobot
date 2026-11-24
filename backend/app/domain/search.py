from collections.abc import Sequence
from typing import Protocol

SEARCH_LIMIT = 20


class NamedItem(Protocol):
    id: int
    name: str


def search_by_id_or_name[T: NamedItem](
    items: Sequence[T], query: str, limit: int = SEARCH_LIMIT
) -> list[T]:
    """Id prefix or case-insensitive name substring; an exact id match goes first."""
    query = query.strip()
    if not query:
        return list(items[:limit])
    folded_query = query.casefold()
    exact: list[T] = []
    others: list[T] = []
    for item in items:
        item_id_text = str(item.id)
        if item_id_text == query:
            exact.append(item)
        elif item_id_text.startswith(query) or folded_query in item.name.casefold():
            others.append(item)
    return (exact + others)[:limit]
