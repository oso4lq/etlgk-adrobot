from dataclasses import dataclass

import pytest

from app.domain.offer_bindings import (
    OfferStateConflictError,
    PinLimitExceededError,
    active_in_order,
    bring_back,
    cancel_draft,
    is_draft,
    mark_published,
    next_sort_order,
    pin,
    published_shares,
    remove,
    stream_notices,
    unpin,
    working_shares,
)


@dataclass
class Binding:
    keitaro_offer_id: int
    sort_order: int
    status: str
    weight: int
    is_pinned: bool
    published_status: str | None
    published_weight: int | None


def published(offer_id: int, weight: int, order: int, *, pinned: bool = False) -> Binding:
    return Binding(offer_id, order, "active", weight, pinned, "active", weight)


def added(offer_id: int, order: int) -> Binding:
    return Binding(offer_id, order, "active", 0, False, None, None)


def removed_binding(offer_id: int, order: int) -> Binding:
    return Binding(offer_id, order, "removed", 0, False, "removed", 0)


def test_clean_stream_is_not_draft():
    assert not is_draft([published(1, 50, 0), published(2, 50, 1)])


def test_unpublished_or_changed_binding_makes_draft():
    assert is_draft([published(1, 100, 0), added(2, 1)])
    changed = published(1, 100, 0)
    changed.weight = 60
    assert is_draft([changed])


def test_remove_greys_out_unpins_and_recalculates():
    bindings = [published(1, 34, 0), published(2, 33, 1), published(3, 33, 2)]
    bindings[1].is_pinned = True
    remove(bindings, bindings[1])
    assert [(b.status, b.weight, b.is_pinned) for b in bindings] == [
        ("active", 50, False),
        ("removed", 0, False),
        ("active", 50, False),
    ]
    assert is_draft(bindings)


def test_remove_twice_is_conflict():
    bindings = [published(1, 100, 0), removed_binding(2, 1)]
    with pytest.raises(OfferStateConflictError) as error:
        remove(bindings, bindings[1])
    assert error.value.message == "Оффер 2 уже удалён из потока"
    assert error.value.code == "offer_state_conflict"
    assert error.value.http_status == 409


def test_bring_back_keeps_pinned_weight():
    bindings = [published(1, 25, 0, pinned=True), published(2, 75, 1), removed_binding(3, 2)]
    bring_back(bindings, bindings[2])
    assert [(b.status, b.weight) for b in bindings] == [
        ("active", 25),
        ("active", 38),
        ("active", 37),
    ]
    assert bindings[0].is_pinned
    assert is_draft(bindings)


def test_bring_back_active_is_conflict():
    bindings = [published(1, 100, 0)]
    with pytest.raises(OfferStateConflictError) as error:
        bring_back(bindings, bindings[0])
    assert error.value.message == "Оффер 1 уже активен в потоке"


def test_pin_and_unpin_change_neither_weights_nor_draft_state():
    bindings = [published(1, 50, 0), published(2, 50, 1)]
    pin(bindings, bindings[0])
    assert bindings[0].is_pinned
    assert [b.weight for b in bindings] == [50, 50]
    assert not is_draft(bindings)
    unpin(bindings, bindings[0])
    assert not bindings[0].is_pinned
    assert [b.weight for b in bindings] == [50, 50]
    assert not is_draft(bindings)


def test_unpin_recalculates_when_all_pinned_and_sum_is_not_100():
    bindings = [published(offer_id, 25, offer_id - 1, pinned=True) for offer_id in (1, 2, 3)]
    unpin(bindings, bindings[0])
    assert bindings[0].is_pinned is False
    assert [b.weight for b in bindings] == [50, 25, 25]
    assert is_draft(bindings) is True
    assert stream_notices(bindings).problems == []


def test_unpin_recalculates_when_pinned_exceed_100():
    bindings = [published(1, 60, 0, pinned=True), published(2, 50, 1, pinned=True)]
    unpin(bindings, bindings[1])
    assert [b.weight for b in bindings] == [60, 40]


def test_pin_over_100_is_rejected():
    bindings = [published(1, 60, 0, pinned=True), published(2, 50, 1)]
    with pytest.raises(PinLimitExceededError) as error:
        pin(bindings, bindings[1])
    assert "станет 110%" in error.value.message
    assert error.value.code == "pinned_sum_exceeds_100"
    assert error.value.http_status == 422
    assert not bindings[1].is_pinned


def test_pin_removed_is_conflict():
    bindings = [removed_binding(1, 0)]
    with pytest.raises(OfferStateConflictError) as error:
        pin(bindings, bindings[0])
    assert error.value.message == "Удалённый оффер 1 нельзя закрепить"


def test_pin_twice_is_noop():
    bindings = [published(1, 100, 0, pinned=True)]
    pin(bindings, bindings[0])
    assert bindings[0].is_pinned


def test_cancel_draft_restores_published_and_returns_unpublished():
    bindings = [published(1, 50, 0), added(2, 1), published(3, 50, 2, pinned=True)]
    remove(bindings, bindings[0])
    unpublished = cancel_draft(bindings)
    assert unpublished == [bindings[1]]
    assert (bindings[0].status, bindings[0].weight) == ("active", 50)
    assert bindings[2].is_pinned
    assert not is_draft([bindings[0], bindings[2]])


def test_mark_published_copies_working_version_including_removed():
    bindings = [published(1, 50, 0), published(2, 50, 1), added(3, 2)]
    remove(bindings, bindings[1])
    mark_published(bindings)
    assert (bindings[1].published_status, bindings[1].published_weight) == ("removed", 0)
    assert (bindings[2].published_status, bindings[2].published_weight) == ("active", 50)
    assert not is_draft(bindings)


def test_published_and_working_shares():
    bindings = [published(1, 100, 0), added(2, 1), removed_binding(3, 2)]
    assert published_shares(bindings) == {1: 100}
    assert working_shares(bindings) == {1: 100, 2: 0}
    remove(bindings, bindings[0])
    assert working_shares(bindings) == {2: 100}
    assert published_shares(bindings) == {1: 100}


def test_active_in_order_and_next_sort_order():
    bindings = [published(2, 50, 5), removed_binding(3, 7), published(1, 50, 2)]
    assert [b.keitaro_offer_id for b in active_in_order(bindings)] == [1, 2]
    assert next_sort_order(bindings) == 8
    assert next_sort_order([]) == 0


def test_notices_empty_stream():
    notices = stream_notices([])
    assert notices.problems == [] and notices.warnings == []


def test_notices_clean_100():
    notices = stream_notices([published(1, 50, 0), published(2, 50, 1)])
    assert notices.problems == [] and notices.warnings == []


def test_notices_all_pinned_not_100():
    notices = stream_notices([published(1, 50, 0, pinned=True), published(2, 40, 1, pinned=True)])
    assert [(n.code, n.message) for n in notices.problems] == [
        ("weights_sum_not_100", "Сумма весов 90%, нужно 100% — открепите оффер")
    ]
    assert notices.warnings == []


def test_notices_fetched_sum_not_100():
    notices = stream_notices([published(1, 25, 0), published(2, 25, 1)])
    assert [(n.code, n.message) for n in notices.problems] == [
        (
            "weights_sum_not_100",
            "Сумма весов 50%, нужно 100% — "
            "веса пересчитаются при добавлении, удалении или возврате оффера",
        )
    ]


def test_notices_pinned_over_100():
    bindings = [published(1, 60, 0, pinned=True), published(2, 60, 1, pinned=True), added(3, 2)]
    notices = stream_notices(bindings)
    assert [(n.code, n.message) for n in notices.problems] == [
        ("weights_sum_not_100", "Сумма весов 120%, нужно 100% — открепите оффер")
    ]


def test_notices_pinned_take_everything():
    notices = stream_notices([published(1, 100, 0, pinned=True), added(2, 1)])
    assert notices.problems == []
    assert [(n.code, n.message) for n in notices.warnings] == [
        (
            "unpinned_offers_get_zero",
            "Закреплённые офферы занимают 100%: незакреплённые получают 0%",
        )
    ]


def test_notices_no_active_offers():
    notices = stream_notices([removed_binding(1, 0), removed_binding(2, 1)])
    assert notices.problems == []
    assert [(n.code, n.message) for n in notices.warnings] == [
        (
            "no_active_offers",
            "В потоке нет активных офферов: после публикации поток в Keitaro останется без офферов",
        )
    ]
