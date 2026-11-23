"""Read-only snapshot of one Keitaro stream, taken before Push and compared after it.

Stage 3 acceptance (CLAUDE.md section 9): Push must change only the offers of a stream. The raw
`GET /streams/{id}` is saved before the first Push and compared with the stream afterwards, so
filters, action, position and everything else are proven untouched. Nothing is written to Keitaro.

Run from backend/:
  python -m tools.stream_snapshot save STREAM_ID PATH
  python -m tools.stream_snapshot diff STREAM_ID PATH [--record NAME]
Keep the raw snapshot outside the repository (it is unsanitised);
only the sanitised `--record` output goes into docs.
Exit codes: 0 - no differences, 1 - differences or a Keitaro error,
2 - configuration or snapshot file error.
"""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.cli.recon import _report_configuration_error, _use_utf8_output
from app.core.config import Settings
from app.keitaro.errors import KeitaroError
from app.keitaro.http_session import KeitaroHttpSession
from tools.compare_campaigns import SECRET_PLACEHOLDER, TRACKER_PLACEHOLDER, compare_values
from tools.keitaro_examples import EXAMPLES_DIR, sanitize, write_example


def stream_settings_differences(before: dict, after: dict) -> list[str]:
    """Differences in everything except the offers; nested ids (filters) are compared too."""

    def normalised(stream: dict) -> dict:
        # Keitaro answers null or "" for an empty action payload depending on how it was saved.
        if stream.get("action_payload") in (None, ""):
            return {**stream, "action_payload": ""}
        return stream

    return compare_values(
        normalised(before), normalised(after), "stream", ignored={"offers"}, nested_ignored=set()
    )


def _record(
    name: str,
    settings: Settings,
    stream_id: int,
    before: dict,
    after: dict,
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
                "path": f"/streams/{stream_id}",
                "query": {},
                "body": None,
            },
            "response": {"status": 200, "body": after},
            "observations": {"before": before, "differences": differences},
        },
        replacements,
    )
    write_example(
        EXAMPLES_DIR,
        name,
        title=f"Проверка потока {stream_id} до и после Push",
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
    parser = argparse.ArgumentParser(description="Снимок потока Keitaro до Push и сравнение после")
    commands = parser.add_subparsers(dest="command", required=True)
    save_parser = commands.add_parser("save", help="сохранить GET /streams/{id} в файл")
    save_parser.add_argument("stream_id", type=int)
    save_parser.add_argument("path", type=Path)
    diff_parser = commands.add_parser("diff", help="сравнить поток в Keitaro со снимком")
    diff_parser.add_argument("stream_id", type=int)
    diff_parser.add_argument("path", type=Path)
    diff_parser.add_argument("--record", metavar="NAME", help="записать в docs/keitaro-examples")
    arguments = parser.parse_args(argv)

    _use_utf8_output()
    try:
        settings = load_settings()
    except ValidationError as error:
        _report_configuration_error(error)
        return 2

    session = build_session(settings)
    try:
        current = session.get(f"/streams/{arguments.stream_id}")
    except KeitaroError as error:
        print(f"Ошибка Keitaro: {error.message}", file=sys.stderr)
        return 1
    finally:
        session.close()

    if arguments.command == "save":
        try:
            arguments.path.parent.mkdir(parents=True, exist_ok=True)
            arguments.path.write_text(
                json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as error:
            print(
                f"Не удалось записать снимок в {arguments.path}: {error.strerror}", file=sys.stderr
            )
            return 2
        print(f"Снимок потока {arguments.stream_id} сохранён")
        return 0

    try:
        before = json.loads(arguments.path.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"Не удалось прочитать снимок {arguments.path}: {error.strerror}", file=sys.stderr)
        return 2
    except ValueError:
        print(f"Снимок {arguments.path} повреждён: это не JSON", file=sys.stderr)
        return 2
    differences = stream_settings_differences(before, current)
    if arguments.record:
        _record(arguments.record, settings, arguments.stream_id, before, current, differences)
    if not differences:
        print("Расхождений нет")
        return 0
    for line in differences:
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
