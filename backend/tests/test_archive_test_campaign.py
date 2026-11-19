from app.keitaro.errors import KeitaroUnavailableError
from app.keitaro.models import KeitaroCampaign, KeitaroStream
from tools.archive_test_campaign import main

PREFIX = "test_oso4lq_"


def _seed(fake, name):
    fake.campaigns[7] = KeitaroCampaign(id=7, name=name, alias="a", type="position", state="active")
    for stream_id in (1, 2):
        fake.streams[stream_id] = KeitaroStream(
            id=stream_id,
            campaign_id=7,
            name=f"stream {stream_id}",
            type="regular",
            position=stream_id,
            state="active",
            schema="redirect",
            action_type="http",
            offers=[],
        )


def _archive_calls(fake):
    return [call for call in fake.calls if call[0].startswith("archive_")]


def _run(fake, make_settings, arguments, prefix=PREFIX):
    return main(
        arguments,
        load_settings=lambda: make_settings(keitaro_write_name_prefix=prefix),
        build_client=lambda settings: fake,
    )


def test_archives_streams_before_campaign(fake, make_settings, capsys):
    _seed(fake, f"{PREFIX}x")
    assert _run(fake, make_settings, ["7", "--confirm"]) == 0
    assert _archive_calls(fake) == [
        ("archive_stream", 1),
        ("archive_stream", 2),
        ("archive_campaign", 7),
    ]
    assert "7" in capsys.readouterr().out


def test_refuses_foreign_campaign(fake, make_settings, capsys):
    _seed(fake, "someone_else")
    assert _run(fake, make_settings, ["7", "--confirm"]) == 3
    assert _archive_calls(fake) == []
    assert "someone_else" not in capsys.readouterr().out


def test_refuses_without_confirm(fake, make_settings):
    _seed(fake, f"{PREFIX}x")
    assert _run(fake, make_settings, ["7"]) == 3
    assert _archive_calls(fake) == []


def test_refuses_without_configured_prefix(fake, make_settings):
    _seed(fake, f"{PREFIX}x")
    assert _run(fake, make_settings, ["7", "--confirm"], prefix="") == 3
    assert _archive_calls(fake) == []


def test_keitaro_error_is_reported_without_traceback(fake, make_settings, capsys):
    _seed(fake, f"{PREFIX}x")
    fake.fail("get_campaign", KeitaroUnavailableError("Keitaro недоступен: таймаут"))
    assert _run(fake, make_settings, ["7", "--confirm"]) == 1
    error_output = capsys.readouterr().err
    assert "Ошибка Keitaro: Keitaro недоступен: таймаут" in error_output
    assert "Traceback" not in error_output
    assert _archive_calls(fake) == []
