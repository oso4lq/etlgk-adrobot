import pytest

from app.services.creator_references import (
    CreatorMisconfiguredError,
    CreatorReferenceResolver,
    CreatorReferences,
)
from tests.fakes import FakeKeitaroClient

EXPECTED = CreatorReferences(1813, "kylovoa.com", 10332, 836)


def test_resolver_finds_ids_by_name_and_caches(make_settings):
    fake = FakeKeitaroClient()
    settings = make_settings(
        campaign_domain="kylovoa.com",
        campaign_group="FORTESTS",
        campaign_traffic_source="FORTESTS",
    )
    resolver = CreatorReferenceResolver(fake, settings)

    assert resolver.resolve() == EXPECTED
    calls_after_first = list(fake.calls)
    assert resolver.resolve() == EXPECTED
    assert fake.calls == calls_after_first


def test_resolver_accepts_numeric_ids(make_settings):
    settings = make_settings(
        campaign_domain="1813", campaign_group="10332", campaign_traffic_source="836"
    )
    assert CreatorReferenceResolver(FakeKeitaroClient(), settings).resolve() == EXPECTED


def test_resolver_reports_every_missing_reference(make_settings):
    settings = make_settings(
        campaign_domain="kylovoa.org", campaign_group="FORTESTS", campaign_traffic_source=""
    )
    with pytest.raises(CreatorMisconfiguredError) as error:
        CreatorReferenceResolver(FakeKeitaroClient(), settings).resolve()
    assert error.value.message == (
        "CAMPAIGN_DOMAIN=kylovoa.org не найден в Keitaro; CAMPAIGN_TRAFFIC_SOURCE не задан"
    )
    assert (error.value.code, error.value.http_status) == ("creator_misconfigured", 503)


def test_failed_resolution_is_not_cached(make_settings):
    fake = FakeKeitaroClient()
    settings = make_settings(
        campaign_domain="kylovoa.com",
        campaign_group="FORTESTS",
        campaign_traffic_source="FORTESTS",
    )
    domains = list(fake.domains)
    fake.domains.clear()
    resolver = CreatorReferenceResolver(fake, settings)
    with pytest.raises(CreatorMisconfiguredError):
        resolver.resolve()

    fake.domains.extend(domains)
    assert resolver.resolve() == EXPECTED
