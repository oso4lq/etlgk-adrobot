import pytest

from app.domain.offer_bindings import PinLimitExceededError, is_draft
from app.services.campaign_fetcher import CampaignFetcher
from app.services.editor_errors import (
    OfferAlreadyInStreamError,
    OfferNotInStreamError,
    StreamNotFoundError,
    StreamWithoutOffersError,
)
from app.services.offer_catalog import OfferNotFoundError
from app.services.stream_editor import StreamEditor


@pytest.fixture
def editor(offer_catalog) -> StreamEditor:
    return StreamEditor(offer_catalog)


@pytest.fixture
def scene(fake, editor_repository, offer_catalog):
    """Fetched campaign: Flow 1 without offers, Flow 2 with 1001/34, 1002/33, 1003/33."""
    for offer_id in range(1001, 1006):
        fake.add_offer(offer_id, f"Offer {offer_id}")
    campaign = fake.add_campaign("test_oso4lq_editor")
    flow_one = fake.add_stream(campaign.id, "Flow 1", 1)
    flow_two = fake.add_stream(campaign.id, "Flow 2", 2, [(1001, 34), (1002, 33), (1003, 33)])
    CampaignFetcher(fake, offer_catalog).fetch(editor_repository, campaign.id)
    # Only calls made by the operations under test must be visible to the assertions.
    fake.calls.clear()
    return campaign, flow_one, flow_two


def reload_stream(db_session, editor_repository, stream_id):
    db_session.expire_all()
    return editor_repository.find_stream(stream_id)


def state(stream):
    return [(o.keitaro_offer_id, o.status, o.weight, o.is_pinned) for o in stream.offers]


def test_add_offer_gives_25_each_and_makes_stream_draft_without_touching_keitaro(
    editor, editor_repository, db_session, fake, scene
):
    _, _, flow_two = scene
    editor.add_offer(editor_repository, flow_two.id, 1004)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert [o.weight for o in stream.offers] == [25, 25, 25, 25]
    added = stream.offers[3]
    assert added.keitaro_offer_id == 1004
    assert added.published_status is None and added.published_weight is None
    assert added.offer_name == "Offer 1004"
    assert is_draft(stream.offers)
    assert all(call == ("list_offers",) for call in fake.calls)
    assert len(fake.streams[flow_two.id].offers) == 3


def test_add_active_offer_is_conflict(editor, editor_repository, scene):
    _, _, flow_two = scene
    with pytest.raises(OfferAlreadyInStreamError):
        editor.add_offer(editor_repository, flow_two.id, 1001)


def test_add_archived_offer_works_as_bring_back(editor, editor_repository, db_session, scene):
    _, _, flow_two = scene
    editor.remove_offer(editor_repository, flow_two.id, 1002)
    editor.add_offer(editor_repository, flow_two.id, 1002)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert state(stream) == [
        (1001, "active", 34, False),
        (1002, "active", 33, False),
        (1003, "active", 33, False),
    ]


def test_add_unknown_offer_is_rejected(editor, editor_repository, db_session, scene):
    _, _, flow_two = scene
    with pytest.raises(OfferNotFoundError):
        editor.add_offer(editor_repository, flow_two.id, 9999)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert len(stream.offers) == 3


def test_add_to_stream_without_offers_is_rejected(editor, editor_repository, scene):
    _, flow_one, _ = scene
    with pytest.raises(StreamWithoutOffersError):
        editor.add_offer(editor_repository, flow_one.id, 1004)


def test_unknown_stream_is_not_found(editor, editor_repository, scene):
    with pytest.raises(StreamNotFoundError):
        editor.add_offer(editor_repository, 424242, 1001)
    with pytest.raises(StreamNotFoundError):
        editor.cancel(editor_repository, 424242)


def test_remove_greys_out_and_recalculates(editor, editor_repository, db_session, fake, scene):
    _, _, flow_two = scene
    editor.remove_offer(editor_repository, flow_two.id, 1002)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert [(o.status, o.weight) for o in stream.offers] == [
        ("active", 50),
        ("removed", 0),
        ("active", 50),
    ]
    assert is_draft(stream.offers)
    assert all(call == ("list_offers",) for call in fake.calls)


def test_bring_back_keeps_pinned_weight(editor, editor_repository, db_session, fake, offer_catalog):
    for offer_id in range(1001, 1005):
        fake.add_offer(offer_id, f"Offer {offer_id}")
    campaign = fake.add_campaign("test_oso4lq_video")
    flow = fake.add_stream(campaign.id, "Flow", 1, [(1001, 25), (1002, 25), (1003, 25), (1004, 25)])
    fetcher = CampaignFetcher(fake, offer_catalog)
    fetcher.fetch(editor_repository, campaign.id)
    fake.set_stream_offers(flow.id, [(1001, 25), (1002, 25)])
    fetcher.fetch(editor_repository, campaign.id)
    editor.pin_offer(editor_repository, flow.id, 1001)
    editor.bring_back_offer(editor_repository, flow.id, 1003)
    stream = reload_stream(db_session, editor_repository, flow.id)
    assert state(stream) == [
        (1001, "active", 25, True),
        (1002, "active", 38, False),
        (1003, "active", 37, False),
        (1004, "removed", 0, False),
    ]


def test_pin_and_unpin_keep_weights_and_stream_clean(editor, editor_repository, db_session, scene):
    _, _, flow_two = scene
    editor.pin_offer(editor_repository, flow_two.id, 1001)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert state(stream) == [
        (1001, "active", 34, True),
        (1002, "active", 33, False),
        (1003, "active", 33, False),
    ]
    assert not is_draft(stream.offers)
    editor.unpin_offer(editor_repository, flow_two.id, 1001)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert state(stream) == [
        (1001, "active", 34, False),
        (1002, "active", 33, False),
        (1003, "active", 33, False),
    ]
    assert not is_draft(stream.offers)


def test_pin_over_100_is_rejected(editor, editor_repository, db_session, fake, offer_catalog):
    fake.add_offer(1001, "Offer 1001")
    fake.add_offer(1002, "Offer 1002")
    campaign = fake.add_campaign("test_oso4lq_pins")
    flow = fake.add_stream(campaign.id, "Flow", 1, [(1001, 60), (1002, 60)])
    CampaignFetcher(fake, offer_catalog).fetch(editor_repository, campaign.id)
    editor.pin_offer(editor_repository, flow.id, 1001)
    with pytest.raises(PinLimitExceededError):
        editor.pin_offer(editor_repository, flow.id, 1002)
    stream = reload_stream(db_session, editor_repository, flow.id)
    assert [o.is_pinned for o in stream.offers] == [True, False]


def test_cancel_restores_published_and_drops_unpublished(
    editor, editor_repository, db_session, fake, offer_catalog, scene
):
    _, _, flow_two = scene
    editor.pin_offer(editor_repository, flow_two.id, 1001)
    editor.add_offer(editor_repository, flow_two.id, 1004)
    editor.remove_offer(editor_repository, flow_two.id, 1002)
    editor.cancel(editor_repository, flow_two.id)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert state(stream) == [
        (1001, "active", 34, True),
        (1002, "active", 33, False),
        (1003, "active", 33, False),
    ]
    assert not is_draft(stream.offers)
    assert offer_catalog.find(1004) is not None
    assert all(call == ("list_offers",) for call in fake.calls)


def test_cancel_clean_stream_changes_nothing(editor, editor_repository, db_session, scene):
    _, _, flow_two = scene
    editor.cancel(editor_repository, flow_two.id)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert [o.weight for o in stream.offers] == [34, 33, 33]
    assert not is_draft(stream.offers)


def test_operation_on_offer_not_in_stream_is_not_found(editor, editor_repository, scene):
    _, _, flow_two = scene
    for operation in (
        editor.remove_offer,
        editor.bring_back_offer,
        editor.pin_offer,
        editor.unpin_offer,
    ):
        with pytest.raises(OfferNotInStreamError):
            operation(editor_repository, flow_two.id, 1005)


def test_changes_are_committed(editor, editor_repository, db_session, scene):
    _, _, flow_two = scene
    returned = editor.remove_offer(editor_repository, flow_two.id, 1002)
    expected = state(returned)
    stream = reload_stream(db_session, editor_repository, flow_two.id)
    assert state(stream) == expected
    assert expected[1] == (1002, "removed", 0, False)
