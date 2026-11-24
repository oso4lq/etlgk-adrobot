"""Integer offer weights inside one stream.

Rules: docs/superpowers/specs/2026-11-18-adrobot-design.md section 5.2 and
docs/decisions.md ("Округление весов", "Крайние случаи закрепления").
Pure functions: no database, no network.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

FULL_WEIGHT = 100


class OfferStatus(StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"


@dataclass(frozen=True)
class WeightSlot:
    status: OfferStatus
    is_pinned: bool
    weight: int


def pinned_total(slots: Sequence[WeightSlot]) -> int:
    return sum(
        slot.weight for slot in slots if slot.status is OfferStatus.ACTIVE and slot.is_pinned
    )


def active_total(slots: Sequence[WeightSlot]) -> int:
    return sum(slot.weight for slot in slots if slot.status is OfferStatus.ACTIVE)


def recalculate_weights(slots: Sequence[WeightSlot]) -> list[int]:
    """New weights in input order (the input is already sorted by sort_order)."""
    unpinned_count = sum(
        1 for slot in slots if slot.status is OfferStatus.ACTIVE and not slot.is_pinned
    )
    # Fetch takes pinned weights from Keitaro as is, so their sum may exceed 100;
    # the remainder must not go negative.
    remainder = max(0, FULL_WEIGHT - pinned_total(slots))
    share, extra = divmod(remainder, unpinned_count) if unpinned_count else (0, 0)

    new_weights: list[int] = []
    for slot in slots:
        if slot.status is not OfferStatus.ACTIVE:
            new_weights.append(0)
        elif slot.is_pinned or not unpinned_count:
            new_weights.append(slot.weight)
        else:
            # The first `extra` unpinned offers get +1, so the sum is exactly 100 and deterministic.
            new_weights.append(share + (1 if extra > 0 else 0))
            extra -= 1
    return new_weights
