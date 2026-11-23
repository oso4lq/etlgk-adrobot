import pytest

from app.keitaro.errors import KeitaroUnavailableError
from app.keitaro.models import KeitaroOffer
from app.services.offer_catalog import OfferCatalog
from tests.fakes import FakeKeitaroClient

TTL_SECONDS = 60.0


class ManualClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def fake() -> FakeKeitaroClient:
    client = FakeKeitaroClient()
    client.offers = [
        KeitaroOffer(id=18813, name="Test offer 18813", state="active"),
        KeitaroOffer(id=20001, name="Flexacil PE", state="active"),
        KeitaroOffer(id=18800, name="Other", state="active"),
    ]
    return client


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def catalog(fake: FakeKeitaroClient, clock: ManualClock) -> OfferCatalog:
    return OfferCatalog(fake, ttl_seconds=TTL_SECONDS, clock=clock)


def ids(offers: list[KeitaroOffer]) -> list[int]:
    return [offer.id for offer in offers]


def test_search_by_id_prefix_puts_exact_id_first(catalog):
    assert ids(catalog.search("18813")) == [18813]
    assert ids(catalog.search("188")) == [18813, 18800]


def test_exact_id_match_goes_before_other_matches(fake, catalog):
    fake.offers = [
        KeitaroOffer(id=1881, name="a", state="active"),
        KeitaroOffer(id=188, name="b", state="active"),
    ]
    assert ids(catalog.search("188")) == [188, 1881]


def test_search_text_query_matches_name_case_insensitively(catalog):
    assert ids(catalog.search("flexacil")) == [20001]
    assert ids(catalog.search("  FLEXACIL ")) == [20001]


def test_search_blank_query_returns_first_offers(catalog):
    assert ids(catalog.search("   ", limit=2)) == [18813, 20001]


def test_search_respects_limit(catalog):
    assert ids(catalog.search("18", limit=1)) == [18813]


def test_offers_are_cached_for_ttl(fake, catalog, clock):
    catalog.search("a")
    catalog.search("b")
    assert fake.calls.count(("list_offers",)) == 1
    clock.now += TTL_SECONDS + 1
    catalog.search("c")
    assert fake.calls.count(("list_offers",)) == 2


def test_find_returns_cached_offer_without_refresh(fake, catalog):
    assert catalog.find(20001).name == "Flexacil PE"
    assert fake.calls.count(("list_offers",)) == 1


def test_find_refreshes_once_on_miss(fake, catalog):
    catalog.search("")
    fake.offers.append(KeitaroOffer(id=30000, name="New", state="active"))
    assert catalog.find(30000).id == 30000
    assert fake.calls.count(("list_offers",)) == 2
    assert catalog.find(99999) is None
    assert fake.calls.count(("list_offers",)) == 3


def test_names_come_from_cache_without_forced_reload(fake, catalog):
    catalog.names()
    catalog.names()
    assert fake.calls.count(("list_offers",)) == 1
    assert catalog.names()[18813] == "Test offer 18813"


def test_keitaro_errors_propagate(fake, catalog):
    fake.fail("list_offers", KeitaroUnavailableError("down"))
    with pytest.raises(KeitaroUnavailableError):
        catalog.search("x")
