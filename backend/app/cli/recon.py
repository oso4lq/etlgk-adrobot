import sys
from collections.abc import Callable, Sequence

from pydantic import ValidationError

from app.core.config import Settings
from app.keitaro.client import KeitaroClient, KeitaroHttpClient
from app.keitaro.errors import KeitaroError
from app.keitaro.references import find_reference


def _section(title: str, lines: Sequence[str]) -> list[str]:
    return [title, *(f"  {line}" for line in lines), ""]


def _resolution_line(setting_name: str, items: Sequence, configured: str) -> str:
    if not configured.strip():
        return f"{setting_name} не задан"
    found = find_reference(items, configured)
    if found is None:
        return f"{setting_name}={configured} → не найдено в Keitaro"
    return f"{setting_name}={configured} → {found.id}"


def render_recon(
    client: KeitaroClient,
    *,
    campaign_domain: str,
    campaign_group: str,
    campaign_traffic_source: str,
) -> str:
    domains = client.list_domains()
    groups = client.list_campaign_groups()
    traffic_sources = client.list_traffic_sources()
    offers = client.list_offers()

    lines: list[str] = []
    lines += _section("Домены", [f"{d.id}  {d.name}  {d.state}" for d in domains])
    lines += _section("Группы кампаний", [f"{g.id}  {g.name}" for g in groups])
    lines += _section(
        "Источники трафика", [f"{s.id}  {s.name}  {s.state}" for s in traffic_sources]
    )
    lines += _section("Офферы", [f"{o.id}  {o.name}  {o.state}" for o in offers])
    lines += _section(
        "Настройки создаватора",
        [
            _resolution_line("CAMPAIGN_DOMAIN", domains, campaign_domain),
            _resolution_line("CAMPAIGN_GROUP", groups, campaign_group),
            _resolution_line("CAMPAIGN_TRAFFIC_SOURCE", traffic_sources, campaign_traffic_source),
        ],
    )
    return "\n".join(lines)


def _use_utf8_output() -> None:
    # Redirected output on Windows uses the locale code page, which cannot encode "→".
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _report_configuration_error(error: ValidationError) -> None:
    # Only variable names: values (the API key) must never reach the console.
    names = sorted({str(problem["loc"][0]).upper() for problem in error.errors() if problem["loc"]})
    print(f"Ошибка конфигурации, проверьте переменные: {', '.join(names)}", file=sys.stderr)


def main(
    *,
    load_settings: Callable[[], Settings] = Settings,
    build_client: Callable[[Settings], KeitaroClient] = KeitaroHttpClient.from_settings,
) -> int:
    _use_utf8_output()
    try:
        settings = load_settings()
    except ValidationError as error:
        _report_configuration_error(error)
        return 2

    try:
        client = build_client(settings)
    except KeitaroError as error:
        print(f"Ошибка Keitaro: {error.message}", file=sys.stderr)
        return 1
    try:
        text = render_recon(
            client,
            campaign_domain=settings.campaign_domain,
            campaign_group=settings.campaign_group,
            campaign_traffic_source=settings.campaign_traffic_source,
        )
    except KeitaroError as error:
        print(f"Ошибка Keitaro: {error.message}", file=sys.stderr)
        return 1
    finally:
        client.close()
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
