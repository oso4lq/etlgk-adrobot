"""Reconcile local offer bindings of one stream with the offers Keitaro returns.

The service converts Keitaro stream offers into RemoteOffer, so the domain
knows nothing about Keitaro formats. Pure functions: no database, no network.
Rules: docs/superpowers/specs/2026-11-18-adrobot-design.md (Fetch Streams).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.offer_bindings import OfferBinding
from app.domain.weights import OfferStatus


@dataclass(frozen=True)
class RemoteOffer:
    offer_id: int
    share: int
    is_active: bool


def merge_remote_offers(offers: Iterable[RemoteOffer]) -> list[RemoteOffer]:
    """One entry per offer id, in order of first appearance.

    Keitaro may list the same offer in several rows; the offer is active if any
    row is active, and its share is the sum of the active rows' shares.
    """
    shares: dict[int, int] = {}
    active: dict[int, bool] = {}
    for offer in offers:
        shares.setdefault(offer.offer_id, 0)
        active.setdefault(offer.offer_id, False)
        if offer.is_active:
            shares[offer.offer_id] += offer.share
            active[offer.offer_id] = True
    return [RemoteOffer(offer_id, shares[offer_id], active[offer_id]) for offer_id in shares]


def remote_state(offer: RemoteOffer) -> tuple[OfferStatus, int]:
    if offer.is_active:
        return OfferStatus.ACTIVE, offer.share
    return OfferStatus.REMOVED, 0


def sync_bindings(
    bindings: Sequence[OfferBinding], remote: Sequence[RemoteOffer]
) -> list[RemoteOffer]:
    """Overwrite both versions of known bindings with Keitaro's state.

    Returns the remote offers we have no binding for, in Keitaro's order; the
    caller creates bindings for them. Keitaro is the source of truth here, so the
    stream ends up clean (working version equals published version).
    """
    remote_by_id = {offer.offer_id: offer for offer in remote}
    known_ids: set[int] = set()
    for binding in bindings:
        known_ids.add(binding.keitaro_offer_id)
        offer = remote_by_id.get(binding.keitaro_offer_id)
        status, weight = remote_state(offer) if offer else (OfferStatus.REMOVED, 0)
        binding.status = binding.published_status = status
        binding.weight = binding.published_weight = weight
        # A removed offer takes no part in weights, so a pin on it would be meaningless.
        if status is OfferStatus.REMOVED:
            binding.is_pinned = False
    return [offer for offer in remote if offer.offer_id not in known_ids]
