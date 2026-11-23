from dataclasses import dataclass

import pytest

from app.domain.offer_bindings import is_draft
from app.domain.offer_sync import RemoteOffer, merge_remote_offers, remote_state, sync_bindings
from app.domain.weights import OfferStatus


@dataclass
class Binding:
    keitaro_offer_id: int
    sort_order: int
    status: str
    weight: int
    is_pinned: bool
    published_status: str | None
    published_weight: int | None


def active_binding(offer_id: int, weight: int, *, pinned: bool = False) -> Binding:
    return Binding(offer_id, offer_id, "active", weight, pinned, "active", weight)


def test_known_active_offer_takes_keitaro_share():
    binding = active_binding(1, 50)

    new_offers = sync_bindings([binding], [RemoteOffer(1, 70, True)])

    assert new_offers == []
    assert (binding.status, binding.weight) == ("active", 70)
    assert (binding.published_status, binding.published_weight) == ("active", 70)


def test_offer_missing_in_keitaro_becomes_removed_and_stream_stays_clean():
    binding = active_binding(1, 25, pinned=True)

    sync_bindings([binding], [])

    assert (binding.status, binding.weight) == ("removed", 0)
    assert (binding.published_status, binding.published_weight) == ("removed", 0)
    assert binding.is_pinned is False
    assert not is_draft([binding])


def test_disabled_offer_becomes_removed():
    binding = active_binding(1, 50, pinned=True)

    sync_bindings([binding], [RemoteOffer(1, 40, False)])

    assert (binding.status, binding.weight) == ("removed", 0)
    assert (binding.published_status, binding.published_weight) == ("removed", 0)
    assert binding.is_pinned is False


def test_removed_offer_back_in_keitaro_is_active():
    binding = Binding(1, 0, "removed", 0, False, "removed", 0)

    sync_bindings([binding], [RemoteOffer(1, 30, True)])

    assert (binding.status, binding.weight) == ("active", 30)
    assert (binding.published_status, binding.published_weight) == ("active", 30)


def test_pins_survive_and_take_keitaro_weight():
    binding = active_binding(1, 25, pinned=True)

    sync_bindings([binding], [RemoteOffer(1, 40, True)])

    assert binding.is_pinned is True
    assert binding.weight == 40


def test_unknown_offers_returned_in_keitaro_order():
    binding = active_binding(1, 100)
    remote = [RemoteOffer(3, 20, True), RemoteOffer(1, 50, True), RemoteOffer(2, 30, True)]

    new_offers = sync_bindings([binding], remote)

    assert [offer.offer_id for offer in new_offers] == [3, 2]


def test_remote_state():
    assert remote_state(RemoteOffer(1, 40, True)) == (OfferStatus.ACTIVE, 40)
    assert remote_state(RemoteOffer(1, 40, False)) == (OfferStatus.REMOVED, 0)


@pytest.mark.parametrize(
    ("offers", "expected"),
    [
        ([(1, 30, True), (2, 70, True), (1, 20, True)], [(1, 50, True), (2, 70, True)]),
        ([(3, 40, False), (3, 60, True)], [(3, 60, True)]),
        ([(4, 10, False), (4, 20, False)], [(4, 0, False)]),
    ],
)
def test_merge_remote_offers(offers, expected):
    merged = merge_remote_offers(RemoteOffer(*item) for item in offers)

    assert [(offer.offer_id, offer.share, offer.is_active) for offer in merged] == expected
