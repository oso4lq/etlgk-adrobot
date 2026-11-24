"""State of offer bindings inside one stream: working vs published version.

Each binding keeps the working version (status, weight) the user edits and the
published version (published_status, published_weight) that matches Keitaro.
A stream is a draft while any binding differs from its published version.
Rules: docs/superpowers/specs/2026-11-18-adrobot-design.md sections 5.1-5.3 and
docs/decisions.md ("Pin — локальная настройка", "Cancel", "Крайние случаи закрепления").
Pure functions: no database, no network.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.core.errors import AppError
from app.domain.notices import Notice
from app.domain.weights import (
    FULL_WEIGHT,
    OfferStatus,
    WeightSlot,
    active_total,
    pinned_total,
    recalculate_weights,
)


class OfferBinding(Protocol):
    """Structural type: the ORM row StreamOffer and plain test dataclasses both fit."""

    keitaro_offer_id: int
    sort_order: int
    status: str
    weight: int
    is_pinned: bool
    published_status: str | None
    published_weight: int | None


class OfferStateConflictError(AppError):
    code = "offer_state_conflict"
    http_status = 409


class PinLimitExceededError(AppError):
    code = "pinned_sum_exceeds_100"
    http_status = 422

    def __init__(self, offer_id: int, total: int) -> None:
        super().__init__(
            f"Нельзя закрепить оффер {offer_id}: "
            f"сумма закреплённых весов станет {total}%, больше {FULL_WEIGHT}%"
        )


@dataclass(frozen=True)
class StreamNotices:
    problems: list[Notice]
    warnings: list[Notice]


def _in_order(bindings: Sequence[OfferBinding]) -> list[OfferBinding]:
    return sorted(bindings, key=lambda binding: binding.sort_order)


def _slots(ordered_bindings: Sequence[OfferBinding]) -> list[WeightSlot]:
    return [
        WeightSlot(OfferStatus(binding.status), binding.is_pinned, binding.weight)
        for binding in ordered_bindings
    ]


def is_draft(bindings: Sequence[OfferBinding]) -> bool:
    for binding in bindings:
        working = (binding.status, binding.weight)
        if working != (binding.published_status, binding.published_weight):
            return True
    return False


def recalculate(bindings: Sequence[OfferBinding]) -> None:
    ordered = _in_order(bindings)
    for binding, weight in zip(ordered, recalculate_weights(_slots(ordered)), strict=True):
        binding.weight = weight


def remove(bindings: Sequence[OfferBinding], binding: OfferBinding) -> None:
    if binding.status == OfferStatus.REMOVED:
        raise OfferStateConflictError(f"Оффер {binding.keitaro_offer_id} уже удалён из потока")
    binding.status = OfferStatus.REMOVED
    binding.weight = 0
    # A removed offer takes no part in weights, so a pin on it would be meaningless.
    binding.is_pinned = False
    recalculate(bindings)


def bring_back(bindings: Sequence[OfferBinding], binding: OfferBinding) -> None:
    if binding.status == OfferStatus.ACTIVE:
        raise OfferStateConflictError(f"Оффер {binding.keitaro_offer_id} уже активен в потоке")
    binding.status = OfferStatus.ACTIVE
    recalculate(bindings)


def pin(bindings: Sequence[OfferBinding], binding: OfferBinding) -> None:
    if binding.status == OfferStatus.REMOVED:
        raise OfferStateConflictError(
            f"Удалённый оффер {binding.keitaro_offer_id} нельзя закрепить"
        )
    if binding.is_pinned:
        return
    total = pinned_total(_slots(_in_order(bindings))) + binding.weight
    if total > FULL_WEIGHT:
        raise PinLimitExceededError(binding.keitaro_offer_id, total)
    binding.is_pinned = True


def unpin(bindings: Sequence[OfferBinding], binding: OfferBinding) -> None:
    if not binding.is_pinned:
        return
    binding.is_pinned = False
    # Without this the "unpin an offer" hint does not lead out of the "sum is not 100"
    # problem: the weights would stay as they were. With sum 100 nothing is touched.
    if active_total(_slots(_in_order(bindings))) != FULL_WEIGHT:
        recalculate(bindings)


def cancel_draft(bindings: Sequence[OfferBinding]) -> list[OfferBinding]:
    """Restore the published version; return never-published bindings for the caller to delete.

    Pins are local settings and are deliberately left untouched.
    """
    unpublished: list[OfferBinding] = []
    for binding in _in_order(bindings):
        if binding.published_status is None or binding.published_weight is None:
            unpublished.append(binding)
            continue
        binding.status = binding.published_status
        binding.weight = binding.published_weight
    return unpublished


def mark_published(bindings: Sequence[OfferBinding]) -> None:
    for binding in bindings:
        binding.published_status = binding.status
        binding.published_weight = binding.weight


def published_shares(bindings: Sequence[OfferBinding]) -> dict[int, int]:
    shares: dict[int, int] = {}
    for binding in _in_order(bindings):
        if binding.published_status == OfferStatus.ACTIVE and binding.published_weight is not None:
            shares[binding.keitaro_offer_id] = binding.published_weight
    return shares


def working_shares(bindings: Sequence[OfferBinding]) -> dict[int, int]:
    shares: dict[int, int] = {}
    for binding in _in_order(bindings):
        if binding.status == OfferStatus.ACTIVE:
            shares[binding.keitaro_offer_id] = binding.weight
    return shares


def active_in_order(bindings: Sequence[OfferBinding]) -> list[OfferBinding]:
    return [binding for binding in _in_order(bindings) if binding.status == OfferStatus.ACTIVE]


def next_sort_order(bindings: Sequence[OfferBinding]) -> int:
    return max((binding.sort_order for binding in bindings), default=-1) + 1


def stream_notices(bindings: Sequence[OfferBinding]) -> StreamNotices:
    problems: list[Notice] = []
    warnings: list[Notice] = []
    if not bindings:
        return StreamNotices(problems, warnings)

    slots = _slots(_in_order(bindings))
    active_slots = [slot for slot in slots if slot.status is OfferStatus.ACTIVE]
    if not active_slots:
        warnings.append(
            Notice(
                "no_active_offers",
                "В потоке нет активных офферов: "
                "после публикации поток в Keitaro останется без офферов",
            )
        )
        return StreamNotices(problems, warnings)

    total = active_total(slots)
    pinned = pinned_total(slots)
    has_unpinned = any(not slot.is_pinned for slot in active_slots)
    if total != FULL_WEIGHT:
        if not has_unpinned or pinned > FULL_WEIGHT:
            advice = "открепите оффер"
        else:
            # Unpinning also recalculates, so it belongs in the hint once something is pinned.
            if any(slot.is_pinned for slot in active_slots):
                advice = (
                    "веса пересчитаются при добавлении, удалении, возврате или откреплении оффера"
                )
            else:
                advice = "веса пересчитаются при добавлении, удалении или возврате оффера"
        problems.append(
            Notice("weights_sum_not_100", f"Сумма весов {total}%, нужно 100% — {advice}")
        )
    if has_unpinned and pinned == FULL_WEIGHT:
        warnings.append(
            Notice(
                "unpinned_offers_get_zero",
                "Закреплённые офферы занимают 100%: незакреплённые получают 0%",
            )
        )
    return StreamNotices(problems, warnings)
