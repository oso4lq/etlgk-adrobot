import threading
import time
from collections.abc import Callable

from app.keitaro.client import KeitaroClient
from app.keitaro.models import KeitaroOffer


class OfferCatalog:
    """Offers from Keitaro cached for a while: autocomplete fires on every keystroke."""

    def __init__(
        self,
        client: KeitaroClient,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        # FastAPI runs sync endpoints in a thread pool, so the cache is shared between threads.
        self._lock = threading.Lock()
        self._offers: list[KeitaroOffer] = []
        self._loaded_at: float | None = None

    def search(self, query: str, limit: int = 20) -> list[KeitaroOffer]:
        with self._lock:
            offers, _ = self._current_offers()
        query = query.strip()
        if not query:
            return offers[:limit]
        folded_query = query.casefold()
        exact: list[KeitaroOffer] = []
        others: list[KeitaroOffer] = []
        for offer in offers:
            offer_id_text = str(offer.id)
            if offer_id_text == query:
                exact.append(offer)
            elif offer_id_text.startswith(query) or folded_query in offer.name.casefold():
                others.append(offer)
        return (exact + others)[:limit]

    def find(self, offer_id: int) -> KeitaroOffer | None:
        with self._lock:
            offers, just_loaded = self._current_offers()
            found = self._find_in(offers, offer_id)
            if found is not None or just_loaded:
                return found
            # The offer may have been created in Keitaro after the cache was filled.
            return self._find_in(self._reload(), offer_id)

    @staticmethod
    def _find_in(offers: list[KeitaroOffer], offer_id: int) -> KeitaroOffer | None:
        for offer in offers:
            if offer.id == offer_id:
                return offer
        return None

    def _current_offers(self) -> tuple[list[KeitaroOffer], bool]:
        """Returns the cached offers and whether they were just loaded from Keitaro."""
        is_fresh = (
            self._loaded_at is not None and self._clock() - self._loaded_at < self._ttl_seconds
        )
        if is_fresh:
            return self._offers, False
        return self._reload(), True

    def _reload(self) -> list[KeitaroOffer]:
        # If Keitaro fails, the exception leaves the old cache and timestamp untouched.
        self._offers = self._client.list_offers()
        self._loaded_at = self._clock()
        return self._offers
