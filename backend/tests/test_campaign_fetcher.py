import pytest

from app.db.models import EditorCampaign, StreamOffer
from app.domain.offer_bindings import is_draft
from app.keitaro.errors import KeitaroUnavailableError
from app.services.campaign_fetcher import CampaignFetcher
from app.services.editor_errors import CampaignNotFetchedError, CampaignNotFoundInKeitaroError
from app.services.offer_catalog import OfferCatalog


@pytest.fixture
def fetcher(fake, offer_catalog) -> CampaignFetcher:
    return CampaignFetcher(fake, offer_catalog)


@pytest.fixture
def scene(fake):
    for offer_id in range(1001, 1006):
        fake.add_offer(offer_id, f"Offer {offer_id}")
    campaign = fake.add_campaign("test_oso4lq_editor")
    flow_one = fake.add_stream(campaign.id, "Flow 1", 1)
    flow_two = fake.add_stream(campaign.id, "Flow 2", 2, [(1001, 34), (1002, 33), (1003, 33)])
    return campaign, flow_one, flow_two


def stream_offers(campaign, position):
    for stream in campaign.streams:
        if stream.position == position:
            return {offer.keitaro_offer_id: offer for offer in stream.offers}
    raise AssertionError(position)


def reload(db_session, editor_repository, campaign_id):
    db_session.expire_all()
    return editor_repository.find_campaign(campaign_id)


def test_fetch_creates_streams_in_position_order(fetcher, editor_repository, db_session, scene):
    campaign, _, _ = scene
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    assert [(s.position, s.name, len(s.offers)) for s in saved.streams] == [
        (1, "Flow 1", 0),
        (2, "Flow 2", 3),
    ]
    offers = saved.streams[1].offers
    assert [o.offer_name for o in offers] == ["Offer 1001", "Offer 1002", "Offer 1003"]
    assert [o.weight for o in offers] == [34, 33, 33]
    for offer in offers:
        assert offer.status == "active"
        assert (offer.published_status, offer.published_weight) == (offer.status, offer.weight)
    assert saved.name == "test_oso4lq_editor"


def test_fetch_takes_weights_from_keitaro_as_is(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fake.set_stream_offers(flow_two.id, [(1001, 25), (1002, 25)])
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    offers = stream_offers(saved, 2)
    assert [o.weight for o in offers.values()] == [25, 25]
    assert not is_draft(saved.streams[1].offers)


def test_fetch_offer_deleted_in_keitaro_turns_removed_and_stream_stays_clean(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    fake.set_stream_offers(flow_two.id, [(1001, 50), (1002, 50)])
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    offers = stream_offers(saved, 2)
    assert (offers[1003].status, offers[1003].weight) == ("removed", 0)
    assert offers[1001].weight == 50
    assert not is_draft(saved.streams[1].offers)


def test_fetch_disabled_offer_is_removed(fetcher, editor_repository, db_session, fake, scene):
    campaign, _, flow_two = scene
    fake.set_stream_offers(flow_two.id, [(1001, 50), (1002, 50), (1003, 0, "disabled")])
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    offer = stream_offers(saved, 2)[1003]
    assert (offer.status, offer.weight) == ("removed", 0)
    assert (offer.published_status, offer.published_weight) == ("removed", 0)


def test_fetch_new_offer_in_keitaro_is_appended_as_active(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    fake.set_stream_offers(flow_two.id, [(1001, 25), (1002, 25), (1003, 25), (1004, 25)])
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    offers = saved.streams[1].offers
    assert [o.keitaro_offer_id for o in offers] == [1001, 1002, 1003, 1004]
    assert [o.sort_order for o in offers] == [0, 1, 2, 3]
    assert offers[3].status == "active" and offers[3].weight == 25
    assert offers[3].published_weight == 25


def test_fetch_keeps_pins_and_takes_pinned_weight_from_keitaro(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    stream_offers(editor_repository.find_campaign(campaign.id), 2)[1001].is_pinned = True
    editor_repository.commit()
    fake.set_stream_offers(flow_two.id, [(1001, 60), (1002, 20), (1003, 20)])
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    pinned = stream_offers(saved, 2)[1001]
    assert pinned.is_pinned and pinned.weight == 60


def make_draft(editor_repository, campaign_id):
    stream = editor_repository.find_campaign(campaign_id).streams[1]
    stream.offers[0].weight = 20
    stream.offers.append(
        StreamOffer(
            keitaro_offer_id=1004,
            offer_name="Offer 1004",
            sort_order=3,
            status="active",
            weight=20,
            is_pinned=False,
            published_status=None,
            published_weight=None,
        )
    )
    editor_repository.commit()


def test_fetch_keeps_draft_stream_and_reports_it(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    make_draft(editor_repository, campaign.id)
    fake.set_stream_offers(flow_two.id, [(1001, 10), (1002, 90)])
    fake.streams[flow_two.id].name = "Flow 2 renamed"
    result = fetcher.fetch(editor_repository, campaign.id)
    assert result.kept_draft_stream_ids == [flow_two.id]
    assert [n.code for n in result.notices] == ["draft_streams_kept"]
    assert "«Flow 2 renamed»" in result.notices[0].message
    saved = reload(db_session, editor_repository, campaign.id)
    assert saved.streams[1].name == "Flow 2 renamed"
    offers = stream_offers(saved, 2)
    assert offers[1004].published_status is None
    assert offers[1001].weight == 20


def test_fetch_force_discards_draft_and_syncs(fetcher, editor_repository, db_session, fake, scene):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    make_draft(editor_repository, campaign.id)
    fake.set_stream_offers(flow_two.id, [(1001, 10), (1002, 90)])
    result = fetcher.fetch(editor_repository, campaign.id, force=True)
    assert result.kept_draft_stream_ids == []
    assert result.notices == []
    saved = reload(db_session, editor_repository, campaign.id)
    offers = stream_offers(saved, 2)
    assert 1004 not in offers
    assert (offers[1001].weight, offers[1002].weight) == (10, 90)
    assert offers[1003].status == "removed"
    assert not is_draft(saved.streams[1].offers)


def test_fetch_deletes_streams_missing_in_keitaro(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    make_draft(editor_repository, campaign.id)
    fake.streams[flow_two.id].state = "deleted"
    result = fetcher.fetch(editor_repository, campaign.id)
    assert [n.code for n in result.notices] == [
        "streams_deleted_in_keitaro",
        "drafts_lost_with_deleted_streams",
    ]
    assert result.notices[0].message.endswith("«Flow 2»")
    saved = reload(db_session, editor_repository, campaign.id)
    assert [s.name for s in saved.streams] == ["Flow 1"]
    assert editor_repository.find_stream(flow_two.id) is None


def test_fetch_merges_duplicate_offer(fetcher, editor_repository, db_session, fake, scene):
    campaign, _, flow_two = scene
    fake.set_stream_offers(flow_two.id, [(1001, 30), (1001, 20), (1002, 50)])
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    offers = stream_offers(saved, 2)
    assert list(offers) == [1001, 1002]
    assert offers[1001].weight == 50


def test_fetch_offer_unknown_to_catalog_gets_fallback_name(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fake.set_stream_offers(flow_two.id, [(1001, 50), (77777, 50)])
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    assert stream_offers(saved, 2)[77777].offer_name == "Оффер 77777"


def test_fetch_unknown_campaign_writes_nothing(fetcher, editor_repository, db_session):
    with pytest.raises(CampaignNotFoundInKeitaroError) as raised:
        fetcher.fetch(editor_repository, 999)
    assert str(raised.value) == "Кампания 999 не найдена в Keitaro"
    db_session.expire_all()
    assert db_session.query(EditorCampaign).count() == 0


def test_fetch_keitaro_failure_leaves_db_unchanged(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    fake.set_stream_offers(flow_two.id, [(1001, 100)])
    fake.fail("get_campaign_streams", KeitaroUnavailableError("down"))
    with pytest.raises(KeitaroUnavailableError):
        fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    assert [o.weight for o in saved.streams[1].offers] == [34, 33, 33]


def test_fetch_never_writes_to_keitaro(fetcher, editor_repository, fake, scene):
    campaign, _, _ = scene
    fetcher.fetch(editor_repository, campaign.id)
    assert {call[0] for call in fake.calls} <= {
        "get_campaign",
        "get_campaign_streams",
        "list_offers",
    }


def test_load_unfetched_campaign_is_not_found(fetcher, editor_repository):
    with pytest.raises(CampaignNotFetchedError) as raised:
        fetcher.load(editor_repository, 5)
    assert raised.value.code == "campaign_not_fetched"
    assert raised.value.http_status == 404
    assert raised.value.message == (
        "Кампания 5 ещё не загружена в редактор — выполните Fetch Streams"
    )


def test_fetch_force_with_unpublished_offer_present_in_keitaro(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    make_draft(editor_repository, campaign.id)
    fake.set_stream_offers(flow_two.id, [(1001, 25), (1002, 25), (1003, 25), (1004, 25)])
    fetcher.fetch(editor_repository, campaign.id, force=True)
    saved = reload(db_session, editor_repository, campaign.id)
    offers = saved.streams[1].offers
    assert [o.keitaro_offer_id for o in offers] == [1001, 1002, 1003, 1004]
    assert (offers[3].status, offers[3].weight) == ("active", 25)
    assert (offers[3].published_status, offers[3].published_weight) == ("active", 25)
    assert not is_draft(offers)


def test_fetch_refreshes_offer_name_from_catalog(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, _ = scene
    fetcher.fetch(editor_repository, campaign.id)
    fake.offers[1].name = "Renamed 1001"
    renewed = CampaignFetcher(fake, OfferCatalog(fake, ttl_seconds=300))
    renewed.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    assert stream_offers(saved, 2)[1001].offer_name == "Renamed 1001"


def test_fetch_keeps_stored_name_when_catalog_lacks_offer(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, _, _ = scene
    fetcher.fetch(editor_repository, campaign.id)
    fake.offers = [offer for offer in fake.offers if offer.id != 1001]
    renewed = CampaignFetcher(fake, OfferCatalog(fake, ttl_seconds=300))
    renewed.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    assert stream_offers(saved, 2)[1001].offer_name == "Offer 1001"


def test_fetch_updates_position_of_existing_stream(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, flow_one, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    fake.streams[flow_one.id].position = 2
    fake.streams[flow_two.id].position = 1
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    assert [s.name for s in saved.streams] == ["Flow 2", "Flow 1"]


def test_fetch_updates_position_of_kept_draft_stream(
    fetcher, editor_repository, db_session, fake, scene
):
    campaign, flow_one, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    make_draft(editor_repository, campaign.id)
    fake.streams[flow_one.id].position = 2
    fake.streams[flow_two.id].position = 1
    fetcher.fetch(editor_repository, campaign.id)
    saved = reload(db_session, editor_repository, campaign.id)
    assert [s.name for s in saved.streams] == ["Flow 2", "Flow 1"]
    assert is_draft(saved.streams[0].offers)
    assert len(saved.streams[0].offers) == 4


def test_fetch_clean_stream_deleted_in_keitaro_reports_only_deletion(
    fetcher, editor_repository, fake, scene
):
    campaign, _, flow_two = scene
    fetcher.fetch(editor_repository, campaign.id)
    fake.streams[flow_two.id].state = "deleted"
    result = fetcher.fetch(editor_repository, campaign.id)
    assert [n.code for n in result.notices] == ["streams_deleted_in_keitaro"]
