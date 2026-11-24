import pytest

from app.domain.weights import (
    OfferStatus,
    WeightSlot,
    active_total,
    pinned_total,
    recalculate_weights,
)

A, R = OfferStatus.ACTIVE, OfferStatus.REMOVED


def slots(*items):
    return [WeightSlot(status, pinned, weight) for status, pinned, weight in items]


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        # video 02:06: a fourth offer is added, nothing pinned
        ([(A, False, 34), (A, False, 33), (A, False, 33), (A, False, 0)], [25, 25, 25, 25]),
        ([(A, False, 0)] * 3, [34, 33, 33]),
        ([(A, False, 0)] * 7, [15, 15, 14, 14, 14, 14, 14]),
        # video 05:24: pinned 25 stays, the two others share the rest
        ([(A, True, 25), (A, False, 25), (A, False, 0)], [25, 38, 37]),
        ([(A, False, 0), (A, True, 25), (A, False, 0)], [38, 25, 37]),
        ([(A, False, 50), (R, False, 30), (A, False, 20)], [50, 0, 50]),
        # a removed pin does not count
        ([(R, True, 30), (A, False, 0), (A, False, 0)], [0, 50, 50]),
        ([(A, True, 40), (A, True, 50)], [40, 50]),  # all pinned: unchanged
        ([(A, True, 100), (A, False, 10), (A, False, 0)], [100, 0, 0]),
        ([(A, True, 60), (A, True, 60), (A, False, 5)], [60, 60, 0]),  # pins from Keitaro over 100
        ([(R, False, 10), (R, False, 0)], [0, 0]),
        ([], []),
    ],
)
def test_recalculate_weights(items, expected):
    assert recalculate_weights(slots(*items)) == expected


def test_unpinned_offers_always_complete_100():
    for pinned in range(0, 101, 7):
        for unpinned_count in range(1, 12):
            items = [(A, True, pinned)] + [(A, False, 0)] * unpinned_count
            assert sum(recalculate_weights(slots(*items))) == 100


def test_totals_count_only_active():
    items = slots((A, True, 30), (R, True, 20), (A, False, 50))
    assert (pinned_total(items), active_total(items)) == (30, 80)
