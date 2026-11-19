"""Helpers for recording real Keitaro requests as committed examples in docs/keitaro-examples."""

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.core.config import REPOSITORY_ROOT

EXAMPLES_DIR = REPOSITORY_ROOT / "docs" / "keitaro-examples"


def sanitize(value: Any, replacements: Mapping[str, str]) -> Any:
    """Replaces secrets (tracker address, API key) inside every string of a JSON-like value."""
    if isinstance(value, str):
        for secret, placeholder in replacements.items():
            # An empty secret (e.g. unset setting) would match between every character.
            if secret:
                value = value.replace(secret, placeholder)
        return value
    if isinstance(value, Mapping):
        return {key: sanitize(item, replacements) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(sanitize(item, replacements) for item in value)
    return value


def keep_only_ids(items: list[dict], allowed_ids: set[int]) -> list[dict]:
    """Drops other users' objects: the Keitaro instance is shared, only ours may be committed."""
    # Compared as strings because Keitaro is not consistent about numeric ids being numbers.
    allowed = {str(identifier) for identifier in allowed_ids}
    return [item for item in items if str(item.get("id")) in allowed]


def redact_fields(items: list[dict], fields: Collection[str]) -> list[dict]:
    """Hides other people's data inside an object we are allowed to commit.

    Only text is masked: the example must still show the real shape and types of the answer.
    """
    return [
        {key: _mask_text(value) if key in fields else value for key, value in item.items()}
        for item in items
    ]


def _mask_text(value: Any) -> Any:
    if isinstance(value, str):
        return "***" if value else value
    if isinstance(value, list):
        return [_mask_text(element) for element in value]
    if isinstance(value, dict):
        return {key: _mask_text(element) for key, element in value.items()}
    return value


def changed_fields(before: dict, after: dict, ignore: set[str]) -> dict[str, tuple[Any, Any]]:
    """Fields whose values differ between two snapshots of the same object, as (before, after)."""
    keys = [*before, *(key for key in after if key not in before)]
    return {
        key: (before.get(key), after.get(key))
        for key in keys
        if key not in ignore and before.get(key) != after.get(key)
    }


def write_example(
    directory: Path,
    name: str,
    *,
    title: str,
    request: dict,
    response: dict,
    observations: dict | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    example = {
        "title": title,
        "request": request,
        "response": response,
        "observations": observations or {},
    }
    path.write_text(json.dumps(example, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@dataclass
class CreatedObjects:
    """Keitaro objects created by the probe itself: the only ones it is allowed to delete."""

    campaign_ids: list[int] = field(default_factory=list)
    stream_ids: list[int] = field(default_factory=list)

    def archive_all(self, client: httpx.Client) -> list[str]:
        """Moves everything to the Keitaro archive and returns errors instead of raising.

        Streams go first: compensation undoes creation in reverse order (campaign, then flows).
        One failed DELETE must not leave the rest of our objects live, hence no exceptions.
        """
        errors: list[str] = []
        for kind, identifiers in (("streams", self.stream_ids), ("campaigns", self.campaign_ids)):
            for identifier in identifiers:
                path = f"/{kind}/{identifier}"
                try:
                    response = client.delete(path)
                except httpx.HTTPError as error:
                    # The exception text may contain the request URL, i.e. the tracker address.
                    errors.append(f"DELETE {path}: {type(error).__name__}")
                    continue
                if not response.is_success:
                    errors.append(f"DELETE {path}: HTTP {response.status_code}")
        return errors
