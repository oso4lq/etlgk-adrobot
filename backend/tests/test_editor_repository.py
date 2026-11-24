from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import EditorStream, StreamOffer
from app.domain.weights import OfferStatus
from app.repositories.editor import EditorRepository

FETCHED_AT = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def make_offer(keitaro_offer_id: int, sort_order: int = 0, **overrides) -> StreamOffer:
    values = {
        "keitaro_offer_id": keitaro_offer_id,
        "offer_name": f"offer {keitaro_offer_id}",
        "sort_order": sort_order,
        "status": "active",
        "weight": 100,
    }
    values.update(overrides)
    return StreamOffer(**values)


def make_stream(keitaro_stream_id: int, position: int = 0) -> EditorStream:
    return EditorStream(keitaro_stream_id=keitaro_stream_id, name="stream", position=position)


@pytest.fixture
def repository(db_session) -> EditorRepository:
    return EditorRepository(db_session)


def test_campaign_streams_and_offers_round_trip_in_order(db_session, repository):
    campaign = repository.add_campaign(10, "campaign", FETCHED_AT)
    late_stream = make_stream(202, position=2)
    early_stream = make_stream(201, position=1)
    early_stream.offers.append(make_offer(1, sort_order=1))
    early_stream.offers.append(make_offer(2, sort_order=0))
    campaign.streams.append(late_stream)
    campaign.streams.append(early_stream)
    repository.commit()
    db_session.expire_all()

    reloaded = repository.find_campaign(10)

    assert reloaded is not None
    assert reloaded.last_fetched_at == FETCHED_AT
    assert [stream.position for stream in reloaded.streams] == [1, 2]
    assert [offer.sort_order for offer in reloaded.streams[0].offers] == [0, 1]
    assert repository.find_stream(201) is reloaded.streams[0]
    assert repository.find_stream(999) is None
    assert repository.find_campaign(999) is None


def test_removing_stream_deletes_its_offers(db_session, repository):
    campaign = repository.add_campaign(10, "campaign", FETCHED_AT)
    stream = make_stream(201)
    stream.offers.append(make_offer(1))
    campaign.streams.append(stream)
    repository.commit()

    campaign.streams.remove(stream)
    repository.commit()

    assert list(db_session.scalars(select(StreamOffer))) == []


def test_same_offer_twice_in_stream_is_rejected(repository):
    campaign = repository.add_campaign(10, "campaign", FETCHED_AT)
    stream = make_stream(201)
    stream.offers.append(make_offer(18813))
    stream.offers.append(make_offer(18813, sort_order=1))
    campaign.streams.append(stream)

    with pytest.raises(IntegrityError):
        repository.commit()


def test_failed_commit_rolls_back_session(repository):
    campaign = repository.add_campaign(10, "campaign", FETCHED_AT)
    stream = make_stream(201)
    stream.offers.append(make_offer(18813))
    stream.offers.append(make_offer(18813, sort_order=1))
    campaign.streams.append(stream)
    with pytest.raises(IntegrityError):
        repository.commit()

    assert repository.find_campaign(10) is None


def test_enum_statuses_are_stored_as_plain_strings(db_session, repository):
    campaign = repository.add_campaign(10, "campaign", FETCHED_AT)
    stream = make_stream(201)
    stream.offers.append(
        make_offer(1, status=OfferStatus.REMOVED, published_status=OfferStatus.ACTIVE)
    )
    campaign.streams.append(stream)
    repository.commit()
    db_session.expire_all()

    offer = repository.find_stream(201).offers[0]

    assert offer.status == "removed"
    assert offer.published_status == "active"
    assert offer.is_pinned is False
    assert type(offer.status) is str
