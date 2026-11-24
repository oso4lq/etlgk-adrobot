"""Read-only field-by-field comparison of two Keitaro campaigns (and their streams).

Used by the stage 2 acceptance: a campaign created through our API is compared with a reference
campaign built by hand in the Keitaro admin. Raw JSON is read (not the typed client models) because
the models drop the fields we need to compare. Nothing is ever written to Keitaro.

Run from backend/:  python -m tools.compare_campaigns REFERENCE_ID CANDIDATE_ID [--record NAME]
Exit codes: 0 - no differences, 1 - differences or a Keitaro error, 2 - configuration error.
"""

import argparse
import sys
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import ValidationError

from app.cli.recon import _report_configuration_error, _use_utf8_output
from app.core.config import Settings
from app.keitaro.errors import KeitaroError
from app.keitaro.http_session import KeitaroHttpSession
from tools.keitaro_examples import EXAMPLES_DIR, sanitize, write_example

# Identity and bookkeeping differ between any two campaigns by definition.
CAMPAIGN_IGNORED_FIELDS = {"id", "alias", "name", "token", "created_at", "updated_at"}
# Ids and links inside streams, filters and offers; names stay compared.
NESTED_IGNORED_FIELDS = {"id", "campaign_id", "stream_id", "oid", "created_at", "updated_at"}
SECRET_PLACEHOLDER = "***"
TRACKER_PLACEHOLDER = "tracker.example.com"


def compare_values(
    reference: Any,
    candidate: Any,
    path: str,
    ignored: set[str],
    nested_ignored: set[str] = NESTED_IGNORED_FIELDS,
) -> list[str]:
    """Field-by-field difference lines; `ignored` applies to this level, `nested_ignored` below."""
    if isinstance(reference, dict) and isinstance(candidate, dict):
        lines: list[str] = []
        for key, reference_value in reference.items():
            if key in ignored:
                continue
            if key not in candidate:
                lines.append(f"{path}.{key}: нет в проверяемой")
                continue
            lines += compare_values(
                reference_value, candidate[key], f"{path}.{key}", nested_ignored, nested_ignored
            )
        for key in candidate:
            if key not in reference and key not in ignored:
                lines.append(f"{path}.{key}: нет в эталоне")
        return lines
    if isinstance(reference, list) and isinstance(candidate, list):
        lines = []
        for index in range(max(len(reference), len(candidate))):
            item_path = f"{path}[{index}]"
            if index >= len(candidate):
                lines.append(f"{item_path}: нет в проверяемой")
            elif index >= len(reference):
                lines.append(f"{item_path}: нет в эталоне")
            else:
                lines += compare_values(
                    reference[index], candidate[index], item_path, ignored, nested_ignored
                )
        return lines
    if reference != candidate:
        return [f"{path}: эталон {reference!r}, проверяемая {candidate!r}"]
    return []


def campaign_differences(
    reference_campaign: dict,
    reference_streams: list[dict],
    candidate_campaign: dict,
    candidate_streams: list[dict],
) -> list[str]:
    lines = compare_values(
        reference_campaign, candidate_campaign, "campaign", CAMPAIGN_IGNORED_FIELDS
    )
    # Position, not id or order of the answer, identifies "the same" stream in two campaigns.
    reference_by_position = {stream["position"]: stream for stream in reference_streams}
    candidate_by_position = {stream["position"]: stream for stream in candidate_streams}
    for position in sorted({*reference_by_position, *candidate_by_position}):
        label = f"stream {position}"
        if position not in candidate_by_position:
            lines.append(f"{label}: нет в проверяемой")
        elif position not in reference_by_position:
            lines.append(f"{label}: нет в эталоне")
        else:
            lines += compare_values(
                reference_by_position[position],
                candidate_by_position[position],
                label,
                NESTED_IGNORED_FIELDS,
            )
    return lines


def _fetch(session: KeitaroHttpSession, campaign_id: int) -> tuple[dict, list[dict]]:
    campaign = session.get(f"/campaigns/{campaign_id}")
    streams = session.get(f"/campaigns/{campaign_id}/streams")
    return campaign, streams


def _without_token(campaign: dict) -> dict:
    return {**campaign, "token": SECRET_PLACEHOLDER} if "token" in campaign else campaign


def _record(
    name: str,
    settings: Settings,
    candidate_id: int,
    reference: tuple[dict, list[dict]],
    candidate: tuple[dict, list[dict]],
    differences: list[str],
) -> None:
    # The bare host is replaced too: it shows up without a scheme in payloads and comments.
    replacements = {
        settings.keitaro_api_key.get_secret_value(): SECRET_PLACEHOLDER,
        settings.keitaro_base_url.rstrip("/"): f"https://{TRACKER_PLACEHOLDER}",
        httpx.URL(settings.keitaro_base_url).host: TRACKER_PLACEHOLDER,
    }
    example = sanitize(
        {
            "request": {
                "method": "GET",
                "path": f"/campaigns/{candidate_id}",
                "query": {},
                "body": None,
            },
            "response": {"status": 200, "body": _without_token(candidate[0])},
            "observations": {
                "reference": {"campaign": _without_token(reference[0]), "streams": reference[1]},
                "candidate_streams": candidate[1],
                "differences": differences,
            },
        },
        replacements,
    )
    write_example(
        EXAMPLES_DIR,
        name,
        title=f"Сравнение кампании {candidate_id} с эталоном",
        request=example["request"],
        response=example["response"],
        observations=example["observations"],
    )


def main(
    argv: list[str] | None = None,
    *,
    load_settings: Callable[[], Settings] = Settings,
    build_session: Callable[[Settings], KeitaroHttpSession] = KeitaroHttpSession.from_settings,
) -> int:
    parser = argparse.ArgumentParser(description="Сравнение двух кампаний Keitaro")
    parser.add_argument("reference_id", type=int)
    parser.add_argument("candidate_id", type=int)
    parser.add_argument("--record", metavar="NAME", help="записать в docs/keitaro-examples")
    arguments = parser.parse_args(argv)

    _use_utf8_output()
    try:
        settings = load_settings()
    except ValidationError as error:
        _report_configuration_error(error)
        return 2

    session = build_session(settings)
    try:
        reference = _fetch(session, arguments.reference_id)
        candidate = _fetch(session, arguments.candidate_id)
    except KeitaroError as error:
        print(f"Ошибка Keitaro: {error.message}", file=sys.stderr)
        return 1
    finally:
        session.close()

    differences = campaign_differences(*reference, *candidate)
    if arguments.record:
        _record(
            arguments.record, settings, arguments.candidate_id, reference, candidate, differences
        )
    if not differences:
        print("Расхождений нет")
        return 0
    for line in differences:
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
