import time
from collections.abc import Callable

from app.core.errors import AppError
from app.domain.search import SEARCH_LIMIT, search_by_id_or_name
from app.keitaro.client import KeitaroClient
from app.keitaro.models import KeitaroOffer
from app.services.ttl_cache import TtlCache


class OfferNotFoundError(AppError):
    code = "offer_not_found"
    http_status = 422

    def __init__(self, offer_id: int) -> None:
        super().__init__(f"Оффер {offer_id} не найден в Keitaro")


class OfferCatalog:
    """Offers from Keitaro cached for a while: autocomplete fires on every keystroke."""

    def __init__(
        self,
        client: KeitaroClient,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache = TtlCache(client.list_offers, ttl_seconds, clock)

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[KeitaroOffer]:
        offers, _ = self._cache.get()
        return search_by_id_or_name(offers, query, limit)

    def find(self, offer_id: int) -> KeitaroOffer | None:
        offers, just_loaded = self._cache.get()
        found = self._find_in(offers, offer_id)
        if found is not None or just_loaded:
            return found
        # The offer may have been created in Keitaro after the cache was filled. The check and
        # the reload are not atomic: concurrent requests may reload twice, which costs only
        # one extra GET /offers.
        return self._find_in(self._cache.reload(), offer_id)

    def names(self) -> dict[int, str]:
        """Offer names by id from the cache; a missing id does not force a reload."""
        offers, _ = self._cache.get()
        names: dict[int, str] = {}
        for offer in offers:
            names[offer.id] = offer.name
        return names

    @staticmethod
    def _find_in(offers: list[KeitaroOffer], offer_id: int) -> KeitaroOffer | None:
        for offer in offers:
            if offer.id == offer_id:
                return offer
        return None
