from app.db.models import CreatedCampaign, CreationStatus
from app.repositories.created_campaigns import CreatedCampaignsRepository


def test_add_pending_is_committed_with_timestamps(db_session):
    entry = CreatedCampaignsRepository(db_session).add_pending("test_oso4lq_a", "DE", 18813)

    assert entry.id is not None
    assert entry.status == CreationStatus.PENDING
    assert entry.created_at.tzinfo is not None
    assert entry.updated_at.tzinfo is not None


def test_save_updates_fields_and_timestamp(db_session):
    repository = CreatedCampaignsRepository(db_session)
    entry = repository.add_pending("test_oso4lq_a", "DE", 18813)

    entry.status = CreationStatus.CREATED
    entry.keitaro_campaign_id = 5
    repository.save(entry)

    db_session.expire_all()
    reloaded = db_session.get(CreatedCampaign, entry.id)
    assert reloaded.status == CreationStatus.CREATED
    assert reloaded.keitaro_campaign_id == 5
    assert reloaded.updated_at.tzinfo is not None
    assert reloaded.updated_at >= reloaded.created_at


def test_list_recent_returns_newest_first(db_session):
    repository = CreatedCampaignsRepository(db_session)
    for name in ("first", "second", "third"):
        repository.add_pending(name, "DE", 1)

    assert [entry.name for entry in repository.list_recent()] == ["third", "second", "first"]
    assert [entry.name for entry in repository.list_recent(limit=2)] == ["third", "second"]
