import logging

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.db.models import CreationStatus
from app.keitaro.errors import KeitaroUnavailableError
from app.repositories.created_campaigns import CreatedCampaignsRepository
from app.services.campaign_creator import CampaignCreationFailedError, CampaignRequest

REQUEST = CampaignRequest("test_oso4lq_j", "DE", 18813)


class FlakyJournal(CreatedCampaignsRepository):
    """Fails chosen saves with a genuine commit error, so the session needs a rollback."""

    def __init__(self, session, fail_on: set[int]) -> None:
        super().__init__(session)
        self._fail_on = fail_on
        self.saves = 0

    def save(self, entry) -> None:
        self.saves += 1
        if self.saves in self._fail_on:
            original_name = entry.name
            entry.name = None  # NOT NULL violation on flush
            try:
                super().save(entry)
            finally:
                entry.name = original_name
        else:
            super().save(entry)


def names_of(fake, *prefixes):
    return [call[0] for call in fake.calls if call[0].startswith(prefixes)]


# Saves: 1 after the campaign, 2 after Flow 1, 3 after Flow 2, 4 final `created` state.
@pytest.mark.parametrize("failing_save", [1, 2, 3, 4])
def test_journal_failure_after_campaign_is_compensated(
    creator, fake, db_session, failing_save, caplog
):
    journal = FlakyJournal(db_session, {failing_save})

    with pytest.raises(CampaignCreationFailedError) as error:
        creator.create(journal, REQUEST)

    assert (error.value.code, error.value.http_status) == ("internal_error", 500)
    assert error.value.message == (
        "Кампания не создана: внутренняя ошибка. Созданное в Keitaro перенесено в архив"
    )
    assert fake.campaigns[1].state == "deleted"
    assert all(stream.state == "deleted" for stream in fake.streams.values())
    archives = names_of(fake, "archive")
    assert archives[-1] == "archive_campaign"
    assert archives.count("archive_stream") == len(fake.streams)
    [entry] = journal.list_recent()
    assert entry.status == CreationStatus.FAILED and entry.error == error.value.message
    assert entry.keitaro_campaign_id == 1 and entry.alias == "alias1"
    assert entry.campaign_url is None
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_failure_to_write_the_final_state_still_reports_compensation(
    creator, fake, db_session, caplog
):
    journal = FlakyJournal(db_session, {1, 2})

    with pytest.raises(CampaignCreationFailedError) as error:
        creator.create(journal, REQUEST)

    assert (error.value.code, error.value.http_status) == ("internal_error", 500)
    assert "перенесено в архив" in error.value.message
    assert fake.campaigns[1].state == "deleted"
    assert "Could not write the final state" in caplog.text


def test_repository_rolls_back_a_failed_commit(db_session):
    journal = CreatedCampaignsRepository(db_session)
    entry = journal.add_pending("test_oso4lq_r", "DE", 1)
    entry.name = None

    with pytest.raises(Exception, match="NOT NULL"):
        journal.save(entry)

    entry.name = "test_oso4lq_r"
    journal.save(entry)  # would raise PendingRollbackError without the rollback


class DyingJournal(CreatedCampaignsRepository):
    """After the chosen save fails, every database statement fails: the database stays down."""

    def __init__(self, session, engine, failing_save: int) -> None:
        super().__init__(session)
        self._failing_save = failing_save
        self.saves = 0
        self.down = False

        @event.listens_for(engine, "before_cursor_execute")
        def die_when_down(connection, cursor, statement, parameters, context, executemany):
            if self.down:
                raise OperationalError(statement, parameters, Exception("database unreachable"))

    def save(self, entry) -> None:
        self.saves += 1
        if self.saves == self._failing_save:
            self.down = True
        super().save(entry)


@pytest.mark.parametrize("failing_save", [1, 2])
def test_compensation_runs_when_the_database_stays_down(
    creator, fake, db_session, failing_save, caplog
):
    journal = DyingJournal(db_session, db_session.get_bind(), failing_save)

    with pytest.raises(CampaignCreationFailedError) as error:
        creator.create(journal, REQUEST)

    assert (error.value.code, error.value.http_status) == ("internal_error", 500)
    assert "перенесено в архив" in error.value.message
    assert "журнал #1" in error.value.message
    assert fake.campaigns[1].state == "deleted"
    assert all(stream.state == "deleted" for stream in fake.streams.values())
    assert names_of(fake, "archive")[-1] == "archive_campaign"
    assert any(
        record.name == "app.creator" and record.levelno == logging.ERROR
        for record in caplog.records
    )


def test_leftovers_are_reported_when_database_is_down_and_archive_fails(creator, fake, db_session):
    fake.fail("archive_campaign", KeitaroUnavailableError("Keitaro недоступен"))
    journal = DyingJournal(db_session, db_session.get_bind(), 1)

    with pytest.raises(CampaignCreationFailedError) as error:
        creator.create(journal, REQUEST)

    assert (error.value.code, error.value.http_status) == ("compensation_failed", 502)
    assert "кампания 1" in error.value.message
    assert "журнал #1" in error.value.message
