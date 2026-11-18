import io
import sys

from app.cli.recon import main, render_recon
from app.core.config import Settings
from app.keitaro.errors import KeitaroAuthError, KeitaroUnavailableError
from app.keitaro.models import KeitaroDomain, KeitaroGroup, KeitaroOffer, KeitaroTrafficSource
from app.keitaro.references import find_reference


class FakeDictionaries:
    def list_domains(self):
        return [KeitaroDomain(id=1813, name="kylovoa.com", state="active")]

    def list_campaign_groups(self):
        return [
            KeitaroGroup(id=1, name="Other", type="campaigns"),
            KeitaroGroup(id=10332, name="FORTESTS", type="campaigns"),
        ]

    def list_traffic_sources(self):
        return [KeitaroTrafficSource(id=836, name="FORTESTS", state="active")]

    def list_offers(self):
        return [KeitaroOffer(id=18813, name="Test offer", state="active")]

    def close(self):
        self.closed = True


class FailingClient(FakeDictionaries):
    def list_domains(self):
        raise KeitaroAuthError("Неверный ключ API Keitaro", keitaro_status=401)


def test_find_reference_by_id_and_by_name():
    groups = FakeDictionaries().list_campaign_groups()
    assert find_reference(groups, "10332").id == 10332
    assert find_reference(groups, " FORTESTS ").id == 10332
    assert find_reference(groups, "fortests") is None
    assert find_reference(groups, "999") is None
    assert find_reference(groups, "  ") is None


def test_render_lists_dictionaries_and_resolves_configuration():
    text = render_recon(
        FakeDictionaries(),
        campaign_domain="kylovoa.com",
        campaign_group="10332",
        campaign_traffic_source="FORTESTS",
    )
    for section in ("Домены", "Группы кампаний", "Источники трафика", "Офферы"):
        assert section in text
    assert any("18813" in line and "Test offer" in line for line in text.splitlines())
    assert "CAMPAIGN_DOMAIN=kylovoa.com → 1813" in text
    assert "CAMPAIGN_GROUP=10332 → 10332" in text
    assert "CAMPAIGN_TRAFFIC_SOURCE=FORTESTS → 836" in text


def test_render_reports_unresolved_and_empty_configuration():
    text = render_recon(
        FakeDictionaries(),
        campaign_domain="",
        campaign_group="Missing",
        campaign_traffic_source="FORTESTS",
    )
    assert "CAMPAIGN_DOMAIN не задан" in text
    assert "CAMPAIGN_GROUP=Missing → не найдено в Keitaro" in text


def test_main_reports_keitaro_error_without_traceback(make_settings, capsys):
    client = FailingClient()
    code = main(load_settings=make_settings, build_client=lambda settings: client)
    captured = capsys.readouterr()
    assert code == 1
    assert "Ошибка Keitaro: Неверный ключ API Keitaro" in captured.err
    assert "Traceback" not in captured.err
    assert client.closed


def test_main_reports_missing_settings(monkeypatch, capsys):
    monkeypatch.delenv("KEITARO_BASE_URL", raising=False)
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)
    code = main(
        load_settings=lambda: Settings(_env_file=None),
        build_client=lambda settings: FakeDictionaries(),
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "KEITARO_BASE_URL" in captured.err and "KEITARO_API_KEY" in captured.err


def test_output_never_contains_api_key(make_settings, capsys):
    client = FakeDictionaries()
    code = main(
        load_settings=lambda: make_settings(campaign_domain="kylovoa.com"),
        build_client=lambda settings: client,
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "test-secret-key-123" not in captured.out + captured.err
    assert "tracker.example.com" not in captured.out + captured.err
    assert client.closed


def test_output_survives_non_utf8_redirect(make_settings, monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1251"))
    code = main(
        load_settings=lambda: make_settings(campaign_domain="kylovoa.com"),
        build_client=lambda settings: FakeDictionaries(),
    )
    sys.stdout.flush()
    assert code == 0
    text = raw.getvalue().decode("utf-8")
    assert "→" in text and "Домены" in text


def test_main_reports_keitaro_error_raised_while_building_client(make_settings, capsys):
    def failing_build(settings):
        raise KeitaroUnavailableError("Keitaro недоступен: ошибка сети")

    code = main(load_settings=make_settings, build_client=failing_build)
    captured = capsys.readouterr()
    assert code == 1
    assert "Ошибка Keitaro: Keitaro недоступен: ошибка сети" in captured.err
    assert "Traceback" not in captured.err
