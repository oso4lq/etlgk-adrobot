import time
from collections.abc import Callable

from app.domain.search import search_by_id_or_name
from app.keitaro.client import KeitaroClient
from app.keitaro.models import KeitaroCampaign
from app.services.ttl_cache import TtlCache

CAMPAIGN_LIST_TTL_SECONDS = 30


class CampaignCatalog:
    """Campaigns for the editor's picker, cached because the picker searches on every keystroke."""

    def __init__(
        self,
        client: KeitaroClient,
        ttl_seconds: float = CAMPAIGN_LIST_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache = TtlCache(client.list_campaigns, ttl_seconds, clock)

    def search(self, query: str) -> list[KeitaroCampaign]:
        campaigns, _ = self._cache.get()
        newest_first = sorted(campaigns, key=lambda campaign: campaign.id, reverse=True)
        return search_by_id_or_name(newest_first, query)
