"""Archives one test campaign and its streams in the shared Keitaro, with guards.

Refuses (exit code 3, nothing written) without --confirm, without KEITARO_WRITE_NAME_PREFIX, or
when the campaign name does not start with that prefix: the tracker is shared, so only our own
test objects may be touched. Objects go to the Keitaro archive, never to `clean_archive`.

Run from backend/:  python -m tools.archive_test_campaign CAMPAIGN_ID --confirm
"""

import argparse
import sys
from collections.abc import Callable

from pydantic import ValidationError

from app.cli.recon import _report_configuration_error, _use_utf8_output
from app.core.config import Settings
from app.keitaro.client import KeitaroClient, KeitaroHttpClient
from app.keitaro.errors import KeitaroError

REFUSED_EXIT_CODE = 3


def _refuse(reason: str) -> int:
    print(f"Отказ: {reason}", file=sys.stderr)
    return REFUSED_EXIT_CODE


def main(
    argv: list[str] | None = None,
    *,
    load_settings: Callable[[], Settings] = Settings,
    build_client: Callable[[Settings], KeitaroClient] = KeitaroHttpClient.from_settings,
) -> int:
    parser = argparse.ArgumentParser(description="Убрать тестовую кампанию Keitaro в архив")
    parser.add_argument("campaign_id", type=int)
    parser.add_argument("--confirm", action="store_true", help="подтвердить запись в Keitaro")
    arguments = parser.parse_args(argv)

    _use_utf8_output()
    try:
        settings = load_settings()
    except ValidationError as error:
        _report_configuration_error(error)
        return 2

    prefix = settings.keitaro_write_name_prefix
    if not arguments.confirm:
        return _refuse("нужен флаг --confirm")
    if not prefix:
        return _refuse("не задан KEITARO_WRITE_NAME_PREFIX")

    client = build_client(settings)
    try:
        campaign = client.get_campaign(arguments.campaign_id)
        if not campaign.name.startswith(prefix):
            # The foreign name is not echoed: it is someone else's data.
            return _refuse(f"имя кампании {campaign.id} не начинается с префикса {prefix}")
        # Streams first, like the creator's compensation: the campaign is archived last.
        for stream in client.get_campaign_streams(campaign.id):
            client.archive_stream(stream.id)
        client.archive_campaign(campaign.id)
    except KeitaroError as error:
        print(f"Ошибка Keitaro: {error.message}", file=sys.stderr)
        return 1
    finally:
        client.close()
    print(f"Убрана в архив кампания {campaign.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
