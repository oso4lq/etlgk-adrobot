import pytest

from app.domain.offer_bindings import is_draft
from app.keitaro.errors import (
    KeitaroNotFoundError,
    KeitaroRejectedError,
    KeitaroUnavailableError,
)
from app.keitaro.models import StreamOfferShare
from app.services.campaign_fetcher import CampaignFetcher
from app.services.editor_errors import (
    KeitaroStreamChangedError,
    StreamNotDraftError,
    StreamNotFoundError,
    WeightsNotReadyError,
    WriteForbiddenError,
)
from app.services.stream_editor import StreamEditor
from app.services.stream_publisher import StreamPublisher

PREFIX = "test_oso4lq_"


@pytest.fixture
def editor(offer_catalog) -> StreamEditor:
    return StreamEditor(offer_catalog)


@pytest.fixture
def publisher(fake, make_settings) -> StreamPublisher:
    return StreamPublisher(fake, make_settings(keitaro_write_name_prefix=PREFIX))


@pytest.fixture
def scene(fake, editor_repository, offer_catalog):
    """Fetched campaign: Flow 1 without offers, Flow 2 with 1001/34, 1002/33, 1003/33."""
    for offer_id in range(1001, 1006):
        fake.add_offer(offer_id, f"Offer {offer_id}")
    campaign = fake.add_campaign(f"{PREFIX}editor")
    flow_one = fake.add_stream(campaign.id, "Flow 1", 1)
    flow_two = fake.add_stream(campaign.id, "Flow 2", 2, [(1001, 34), (1002, 33), (1003, 33)])
    CampaignFetcher(fake, offer_catalog).fetch(editor_repository, campaign.id)
    fake.calls.clear()
    return campaign, flow_one, flow_two


def reload_stream(db_session, editor_repository, stream_id):
    db_session.expire_all()
    return editor_repository.find_stream(stream_id)


def keitaro_shares(fake, stream_id):
    return [(o.offer_id, o.share) for o in fake.streams[stream_id].offers]


def write_calls(fake):
    return [call[0] for call in fake.calls if call[0] == "replace_stream_offers"]


def test_push_sends_active_offers_in_order_and_publishes(
    editor, publisher, editor_repository, db_session, fake, scene
):
    _, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    publisher.push(editor_repository, flow_two.id)
    assert fake.calls[-1] == (
        "replace_stream_offers",
        flow_two.id,
        (
            StreamOfferShare(1001, 25),
            StreamOfferShare(1002, 25),
            StreamOfferShare(1003, 25),
            StreamOfferShare(1004, 25),
        ),
    )
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert not is_draft(stream.offers)
    assert keitaro_shares(fake, flow_two.id) == [(1001, 25), (1002, 25), (1003, 25), (1004, 25)]


def test_push_writes_nothing_but_offers(editor, publisher, editor_repository, fake, scene):
    _, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    publisher.push(editor_repository, flow_two.id)
    names = [call[0] for call in fake.calls]
    assert [name for name in names if not name.startswith("get_")] == ["replace_stream_offers"]


def test_push_removed_offer_disappears_from_keitaro_and_stays_archived(
    editor, publisher, editor_repository, db_session, fake, scene
):
    _, _, flow_two = scene
    editor.remove_offer(editor_repository, flow_two.id, 1002)
    publisher.push(editor_repository, flow_two.id)
    assert keitaro_shares(fake, flow_two.id) == [(1001, 50), (1003, 50)]
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    removed = stream.offers[1]
    assert (removed.keitaro_offer_id, removed.status, removed.weight) == (1002, "removed", 0)
    assert (removed.published_status, removed.published_weight) == ("removed", 0)
    assert not is_draft(stream.offers)


def test_push_stream_without_active_offers_sends_empty_list(
    editor, publisher, editor_repository, db_session, fake, scene
):
    _, _, flow_two = scene
    for offer_id in (1001, 1002, 1003):
        editor.remove_offer(editor_repository, flow_two.id, offer_id)
    publisher.push(editor_repository, flow_two.id)
    assert fake.calls[-1] == ("replace_stream_offers", flow_two.id, ())
    assert keitaro_shares(fake, flow_two.id) == []
    assert not is_draft(reload_stream(db_session, editor_repository, flow_two.id).offers)


def test_push_clean_stream_is_rejected(publisher, editor_repository, fake, scene):
    _, _, flow_two = scene
    with pytest.raises(StreamNotDraftError):
        publisher.push(editor_repository, flow_two.id)
    assert fake.calls == []


def test_push_unknown_stream_is_not_found(publisher, editor_repository, scene):
    with pytest.raises(StreamNotFoundError):
        publisher.push(editor_repository, 424242)


def test_push_with_weights_not_100_is_rejected(
    editor, publisher, editor_repository, fake, offer_catalog
):
    fake.add_offer(1001, "Offer 1001")
    fake.add_offer(1002, "Offer 1002")
    campaign = fake.add_campaign(f"{PREFIX}sum")
    flow = fake.add_stream(campaign.id, "Flow", 1, [(1001, 40), (1002, 50)])
    CampaignFetcher(fake, offer_catalog).fetch(editor_repository, campaign.id)
    editor.pin_offer(editor_repository, flow.id, 1001)
    editor.pin_offer(editor_repository, flow.id, 1002)
    editor.remove_offer(editor_repository, flow.id, 1002)
    fake.calls.clear()
    with pytest.raises(WeightsNotReadyError) as raised:
        publisher.push(editor_repository, flow.id)
    assert raised.value.code == "weights_sum_not_100"
    assert "40" in str(raised.value)
    assert fake.calls == []


def test_push_refused_for_campaign_without_prefix(
    editor, publisher, editor_repository, fake, offer_catalog
):
    fake.add_offer(1001, "Offer 1001")
    fake.add_offer(1002, "Offer 1002")
    campaign = fake.add_campaign("other_x")
    flow = fake.add_stream(campaign.id, "Flow", 1, [(1001, 50), (1002, 50)])
    CampaignFetcher(fake, offer_catalog).fetch(editor_repository, campaign.id)
    editor.remove_offer(editor_repository, flow.id, 1002)
    fake.calls.clear()
    with pytest.raises(WriteForbiddenError) as raised:
        publisher.push(editor_repository, flow.id)
    assert PREFIX in str(raised.value)
    assert fake.calls == []


def test_push_refused_when_campaign_lost_prefix_after_fetch(
    editor, publisher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    fake.campaigns[campaign.id].name = "renamed"
    with pytest.raises(WriteForbiddenError):
        publisher.push(editor_repository, flow_two.id)
    assert write_calls(fake) == []
    # Nothing is committed on refusal, not even the freshly read name.
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert stream.campaign.name == f"{PREFIX}editor"
    assert is_draft(stream.offers)


def test_push_without_prefix_setting_is_allowed(
    editor, editor_repository, fake, make_settings, offer_catalog
):
    fake.add_offer(1001, "Offer 1001")
    fake.add_offer(1002, "Offer 1002")
    campaign = fake.add_campaign("any_name")
    flow = fake.add_stream(campaign.id, "Flow", 1, [(1001, 50), (1002, 50)])
    CampaignFetcher(fake, offer_catalog).fetch(editor_repository, campaign.id)
    editor.remove_offer(editor_repository, flow.id, 1002)
    StreamPublisher(fake, make_settings(keitaro_write_name_prefix="")).push(
        editor_repository, flow.id
    )
    assert keitaro_shares(fake, flow.id) == [(1001, 100)]


def test_push_stores_live_campaign_name_on_success(
    editor, publisher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    fake.campaigns[campaign.id].name = f"{PREFIX}renamed"
    publisher.push(editor_repository, flow_two.id)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert stream.campaign.name == f"{PREFIX}renamed"


def test_push_conflict_when_keitaro_offers_changed(
    editor, publisher, editor_repository, db_session, fake, scene
):
    _, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    fake.set_stream_offers(flow_two.id, [(1001, 100)])
    with pytest.raises(KeitaroStreamChangedError) as raised:
        publisher.push(editor_repository, flow_two.id)
    assert str(raised.value) == (
        "Офферы потока в Keitaro изменились после последнего Fetch Streams — "
        "выполните Fetch Streams с отбросом черновика"
    )
    assert write_calls(fake) == []
    assert is_draft(reload_stream(db_session, editor_repository, flow_two.id).offers)


def test_push_to_disabled_stream_writes_offers_and_keeps_it_disabled(
    editor, publisher, editor_repository, db_session, fake, scene
):
    _, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    fake.streams[flow_two.id].state = "disabled"
    publisher.push(editor_repository, flow_two.id)
    assert keitaro_shares(fake, flow_two.id) == [(1001, 25), (1002, 25), (1003, 25), (1004, 25)]
    assert fake.streams[flow_two.id].state == "disabled"
    assert not is_draft(reload_stream(db_session, editor_repository, flow_two.id).offers)


def test_push_refused_when_campaign_archived_in_keitaro(
    editor, publisher, editor_repository, db_session, fake, scene
):
    campaign, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    # Streams of an archived campaign stay active (decisions В7): only get_campaign stops the PUT.
    fake.campaigns[campaign.id].state = "deleted"
    with pytest.raises(KeitaroNotFoundError) as raised:
        publisher.push(editor_repository, flow_two.id)
    assert raised.value.code == "keitaro_not_found"
    assert write_calls(fake) == []
    assert is_draft(reload_stream(db_session, editor_repository, flow_two.id).offers)


@pytest.mark.parametrize("how", ["archived", "missing", "foreign_campaign"])
def test_push_conflict_when_stream_archived_or_missing(
    how, editor, publisher, editor_repository, fake, scene
):
    campaign, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    if how == "archived":
        fake.streams[flow_two.id].state = "deleted"
    elif how == "missing":
        del fake.streams[flow_two.id]
    else:
        fake.streams[flow_two.id].campaign_id = campaign.id + 100
    with pytest.raises(KeitaroStreamChangedError) as raised:
        publisher.push(editor_repository, flow_two.id)
    assert str(raised.value) == "Поток удалён в Keitaro — выполните Fetch Streams"
    assert write_calls(fake) == []


def test_push_keitaro_error_leaves_draft(
    editor, publisher, editor_repository, db_session, fake, scene
):
    _, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    fake.fail("replace_stream_offers", KeitaroRejectedError("bad", 422))
    with pytest.raises(KeitaroRejectedError):
        publisher.push(editor_repository, flow_two.id)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert is_draft(stream.offers)
    assert [(o.published_status, o.published_weight) for o in stream.offers] == [
        ("active", 34),
        ("active", 33),
        ("active", 33),
        (None, None),
    ]


def test_push_after_lost_response_reconciles_without_second_put(
    editor, publisher, editor_repository, db_session, fake, scene
):
    _, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    fake.fail("replace_stream_offers", KeitaroUnavailableError("timeout"), after_applying=True)
    with pytest.raises(KeitaroUnavailableError):
        publisher.push(editor_repository, flow_two.id)
    fake.calls.clear()
    publisher.push(editor_repository, flow_two.id)
    assert write_calls(fake) == []
    assert not is_draft(reload_stream(db_session, editor_repository, flow_two.id).offers)


def test_push_keeps_pins(editor, publisher, editor_repository, db_session, scene):
    _, _, flow_two = scene
    editor.pin_offer(editor_repository, flow_two.id, 1001)
    editor.add_offer(editor_repository, flow_two.id, 1004)
    publisher.push(editor_repository, flow_two.id)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert [(o.keitaro_offer_id, o.weight, o.is_pinned) for o in stream.offers] == [
        (1001, 34, True),
        (1002, 22, False),
        (1003, 22, False),
        (1004, 22, False),
    ]
