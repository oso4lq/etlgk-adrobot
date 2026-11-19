import pytest

from app.db.models import CreationStatus
from app.keitaro.errors import (
    KeitaroAliasTakenError,
    KeitaroForbiddenError,
    KeitaroRejectedError,
    KeitaroUnavailableError,
)
from app.services.campaign_creator import (
    MAX_ALIAS_ATTEMPTS,
    CampaignCreationFailedError,
    CampaignCreator,
    CampaignRequest,
)

REQUEST = CampaignRequest("test_oso4lq_c", "DE", 18813)


def create_expecting_failure(creator: CampaignCreator, journal):
    with pytest.raises(CampaignCreationFailedError) as error:
        creator.create(journal, REQUEST)
    [entry] = journal.list_recent()
    return error.value, entry


def create_expecting_failure_of_last(creator: CampaignCreator, journal):
    with pytest.raises(CampaignCreationFailedError) as error:
        creator.create(journal, REQUEST)
    return error.value, journal.list_recent()[0]


def names_of(fake, *prefixes):
    return [call[0] for call in fake.calls if call[0].startswith(prefixes)]


def test_failure_on_country_stream_archives_campaign(creator, fake, journal):
    fake.fail(
        "create_country_redirect_stream", KeitaroRejectedError("Keitaro отклонил запрос: x", 422)
    )

    error, entry = create_expecting_failure(creator, journal)

    assert (error.code, error.http_status) == ("keitaro_rejected", 422)
    assert entry.status == CreationStatus.FAILED and entry.error == error.message
    assert error.message == (
        "Кампания не создана: Keitaro отклонил запрос: x. Созданное в Keitaro перенесено в архив"
    )
    assert ("archive_campaign", entry.keitaro_campaign_id) in fake.calls
    assert fake.campaigns[entry.keitaro_campaign_id].state == "deleted"


def test_failure_on_offers_stream_archives_streams_before_campaign(creator, fake, journal):
    fake.fail(
        "create_offers_stream", KeitaroUnavailableError("Keitaro недоступен"), after_applying=True
    )

    error, entry = create_expecting_failure(creator, journal)

    assert (error.code, error.http_status) == ("keitaro_unavailable", 502)
    assert entry.status == CreationStatus.FAILED
    # Flow 2 is unknown to the journal: it is found through get_campaign_streams.
    archived_streams = [call[1] for call in fake.calls if call[0] == "archive_stream"]
    assert sorted(archived_streams) == [1, 2]
    assert names_of(fake, "archive") == ["archive_stream", "archive_stream", "archive_campaign"]
    assert all(stream.state == "deleted" for stream in fake.streams.values())


def test_lost_campaign_response_is_found_by_alias_and_archived(creator, fake, journal):
    fake.fail("create_campaign", KeitaroUnavailableError("Keitaro недоступен"), after_applying=True)

    error, entry = create_expecting_failure(creator, journal)

    assert entry.status == CreationStatus.FAILED and error.code == "keitaro_unavailable"
    assert entry.alias == "alias1" and entry.keitaro_campaign_id == 1
    assert ("archive_campaign", 1) in fake.calls
    assert fake.campaigns[1].state == "deleted"


def test_lookup_ignores_campaigns_with_other_aliases(creator, fake, journal):
    creator.create(journal, CampaignRequest("test_oso4lq_old", "DE", 18813))
    fake.fail("create_campaign", KeitaroUnavailableError("Keitaro недоступен"))

    with pytest.raises(CampaignCreationFailedError):
        creator.create(journal, REQUEST)

    assert not names_of(fake, "archive")
    assert fake.campaigns[1].state == "active"


def test_campaign_not_created_means_nothing_to_archive(creator, fake, journal):
    fake.fail("create_campaign", KeitaroUnavailableError("Keitaro недоступен"))

    error, entry = create_expecting_failure(creator, journal)

    assert not names_of(fake, "archive")
    assert entry.status == CreationStatus.FAILED
    assert (
        entry.error
        == error.message
        == ("Кампания не создана: Keitaro недоступен. Кампания с alias alias1 в Keitaro не найдена")
    )
    assert (error.code, error.http_status) == ("keitaro_unavailable", 502)


def test_alias_taken_every_time_fails_without_writes(creator, fake, journal):
    taken = KeitaroAliasTakenError("taken", 422, frozenset({"alias"}))
    fake.fail("create_campaign", taken, times=MAX_ALIAS_ATTEMPTS)

    error, entry = create_expecting_failure(creator, journal)

    assert names_of(fake, "create").count("create_campaign") == 3
    assert not names_of(fake, "archive")
    assert (error.code, error.http_status) == ("keitaro_rejected", 422)
    assert error.message == "Кампания не создана: Не удалось подобрать свободный alias за 3 попытки"
    assert entry.status == CreationStatus.FAILED and entry.error == error.message


def test_rejected_campaign_is_not_compensated(creator, fake, journal):
    fake.fail("create_campaign", KeitaroForbiddenError("Доступ запрещён", 403))

    error, entry = create_expecting_failure(creator, journal)

    assert (error.code, error.http_status) == ("keitaro_forbidden", 403)
    assert entry.status == CreationStatus.FAILED
    assert not names_of(fake, "list_campaigns", "archive")


def test_failed_compensation_is_recorded_for_manual_cleanup(creator, fake, journal):
    fake.fail("create_offers_stream", KeitaroRejectedError("отказ", 422))
    fake.fail("archive_campaign", KeitaroUnavailableError("Keitaro недоступен"))

    error, entry = create_expecting_failure(creator, journal)

    assert entry.status == CreationStatus.COMPENSATION_FAILED
    assert (error.code, error.http_status) == ("compensation_failed", 502)
    assert entry.error == error.message
    assert f"кампания {entry.keitaro_campaign_id}" in error.message
    assert f"журнал #{entry.id}" in error.message
    assert "Кампания не создана: отказ. Не удалось убрать в архив:" in error.message
    # The stream was archived, so only the campaign is left over.
    assert "потоки" not in error.message
    assert entry.keitaro_campaign_id is not None


def test_unreadable_stream_list_is_reported_as_leftover(creator, fake, journal):
    fake.fail(
        "create_offers_stream", KeitaroUnavailableError("Keitaro недоступен"), after_applying=True
    )
    fake.fail("get_campaign_streams", KeitaroUnavailableError("Keitaro недоступен"))

    error, entry = create_expecting_failure(creator, journal)

    assert entry.status == CreationStatus.COMPENSATION_FAILED
    assert "список потоков не прочитан" in error.message
    # Flow 1 and the campaign are archived anyway.
    assert fake.streams[1].state == "deleted"
    assert fake.campaigns[entry.keitaro_campaign_id].state == "deleted"


def test_stream_archive_failure_does_not_stop_others_and_is_listed(creator, fake, journal):
    fake.fail("create_offers_stream", KeitaroRejectedError("отказ", 422))
    fake.fail("archive_stream", KeitaroUnavailableError("Keitaro недоступен"))

    error, entry = create_expecting_failure(creator, journal)

    assert entry.status == CreationStatus.COMPENSATION_FAILED
    assert f"потоки {entry.country_stream_id}" in error.message
    assert "кампания " not in error.message  # the campaign itself was archived


def test_alias_lookup_failure_is_reported_as_compensation_failed(creator, fake, journal):
    fake.fail("create_campaign", KeitaroUnavailableError("Keitaro недоступен"))
    fake.fail("list_campaigns", KeitaroUnavailableError("Keitaro недоступен"))

    error, entry = create_expecting_failure(creator, journal)

    assert entry.status == CreationStatus.COMPENSATION_FAILED
    assert (error.code, error.http_status) == ("compensation_failed", 502)
    assert "alias1" in error.message and f"журнал #{entry.id}" in error.message
    assert entry.error == error.message


def test_unexpected_error_is_logged_at_error_level(creator, fake, journal, caplog):
    fake.fail("create_offers_stream", RuntimeError("boom"))

    create_expecting_failure(creator, journal)

    records = [r for r in caplog.records if r.name == "app.creator"]
    assert [r.levelname for r in records] == ["ERROR"]
    assert records[0].exc_info is not None


def test_keitaro_failure_is_not_logged_by_the_creator(creator, fake, journal, caplog):
    fake.fail("create_offers_stream", KeitaroRejectedError("отказ", 422))

    create_expecting_failure(creator, journal)

    assert not [r for r in caplog.records if r.name == "app.creator"]


def test_unexpected_error_is_compensated_and_reported_as_internal(creator, fake, journal):
    fake.fail("create_offers_stream", RuntimeError("boom"))

    error, entry = create_expecting_failure(creator, journal)

    assert (error.code, error.http_status) == ("internal_error", 500)
    assert "boom" not in error.message and "boom" not in entry.error
    assert error.message.startswith("Кампания не создана: внутренняя ошибка")
    assert entry.status == CreationStatus.FAILED
    assert ("archive_campaign", entry.keitaro_campaign_id) in fake.calls


def test_lookup_does_not_archive_campaign_with_our_alias_but_other_name(creator, fake, journal):
    creator.create(journal, CampaignRequest("test_oso4lq_old", "DE", 18813))
    fake.campaigns[1].alias = "alias2"  # the next alias the creator will generate
    fake.fail("create_campaign", KeitaroUnavailableError("Keitaro недоступен"))

    error, entry = create_expecting_failure_of_last(creator, journal)

    assert entry.status == CreationStatus.FAILED
    assert not names_of(fake, "archive")
    assert fake.campaigns[1].state == "active"
    assert error.message.endswith("Кампания с alias alias2 в Keitaro не найдена")
