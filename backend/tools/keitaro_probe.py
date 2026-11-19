"""Reconnaissance of the real Keitaro: records request/response pairs into docs/keitaro-examples.

The Keitaro instance is shared with other users, so the probe writes only to objects it creates
itself in this run (named with KEITARO_WRITE_NAME_PREFIX) and archives all of them before exiting.
Nothing secret leaves the process: every recorded or printed value goes through `sanitize`.

Run from backend/:  python -m tools.keitaro_probe --confirm-writes
"""

import argparse
import json
import secrets
import string
import sys
from collections.abc import Collection
from dataclasses import dataclass, replace
from typing import Any

import httpx

from app.core.config import Settings
from tools.keitaro_examples import (
    EXAMPLES_DIR,
    CreatedObjects,
    changed_fields,
    keep_only_ids,
    redact_fields,
    sanitize,
    write_example,
)

# The only offer visible to the test user (docs/decisions.md, "один оффер").
PROBE_OFFER_ID = 18813
TEST_COUNTRY = "DE"
PROBE_REJECTED_COUNTRY = "FR"
ALIAS_LENGTH = 6
NOT_FOUND_CAMPAIGN_ID = 999999999
INVALID_API_KEY = "invalid-key-for-probe"
NON_JSON_BODY_LIMIT = 300
SHOWN_BODY_LIMIT = 1000
# A PUT with only "offers" is expected to change nothing but the offers and the timestamp.
STREAM_FIELDS_ALLOWED_TO_CHANGE = {"updated_at", "offers"}
# Our domain is shared: its default campaign and its group belong to other users.
DOMAIN_FOREIGN_FIELDS = {"default_campaign", "group"}
# The offer is the instance owner's product: its name, targeting and lander location are their
# business data, not something a public repository should carry. Ids and the shape stay.
OFFER_OWNER_FIELDS = {
    "name",
    "group",
    "country",
    "affiliate_network",
    "action_options",
    "local_path",
    "preview_path",
}


class ProbeAborted(Exception):
    """A step the rest of the probe depends on failed; cleanup still runs."""


@dataclass(frozen=True)
class Exchange:
    method: str
    path: str
    query: dict
    body: Any
    status: int
    response_body: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass(frozen=True)
class PutResult:
    put: Exchange
    after: Any
    changes: dict


def make_client(settings: Settings, api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=f"{settings.keitaro_base_url}/admin_api/v1",
        headers={"Api-Key": api_key},
        timeout=settings.keitaro_timeout_seconds,
    )


def call(
    client: httpx.Client, method: str, path: str, *, query: dict | None = None, body: Any = None
) -> Exchange:
    """One Keitaro request; HTTP error statuses are data here, not exceptions."""
    response = client.request(method, path, params=query, json=body)
    try:
        response_body = response.json()
    except ValueError:
        # Some Keitaro errors (e.g. unknown id) are nginx HTML pages, not JSON.
        response_body = response.text[:NON_JSON_BODY_LIMIT]
    return Exchange(method, path, query or {}, body, response.status_code, response_body)


def random_alias() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(ALIAS_LENGTH))


def find_configured(items: list[dict], configured: str, what: str) -> int:
    """Settings name a Keitaro directory entry either by its name or by its id."""
    matches = [item for item in items if configured in (item.get("name"), str(item.get("id")))]
    if len(matches) != 1:
        raise ProbeAborted(f"{what} {configured!r}: expected one match, found {len(matches)}")
    return int(matches[0]["id"])


def offer_rows(stream: Any) -> list[dict]:
    if not isinstance(stream, dict):
        return []
    return [
        {key: offer.get(key) for key in ("id", "offer_id", "share", "state")}
        for offer in stream.get("offers") or []
    ]


class KeitaroProbe:
    def __init__(self, settings: Settings, client: httpx.Client) -> None:
        self.settings = settings
        self.client = client
        self.prefix = settings.keitaro_write_name_prefix
        self.replacements = {
            httpx.URL(settings.keitaro_base_url).host: "tracker.example.com",
            settings.keitaro_api_key.get_secret_value(): "***",
        }
        # Everything created in this run; cleanup asks Keitaro which of them are still live.
        self.created = CreatedObjects()
        self.stop_conditions: list[str] = []

    def call(
        self, method: str, path: str, *, query: dict | None = None, body: Any = None
    ) -> Exchange:
        return call(self.client, method, path, query=query, body=body)

    def show(self, value: Any) -> str:
        # Truncated: an unexpected body may be a whole list of other users' objects.
        return json.dumps(sanitize(value, self.replacements))[:SHOWN_BODY_LIMIT]

    def record(
        self, name: str, title: str, exchange: Exchange, observations: dict | None = None
    ) -> None:
        request = {
            "method": exchange.method,
            "path": exchange.path,
            "query": exchange.query,
            "body": exchange.body,
        }
        response = {"status": exchange.status, "body": exchange.response_body}
        write_example(
            EXAMPLES_DIR,
            name,
            title=title,
            request=sanitize(request, self.replacements),
            response=sanitize(response, self.replacements),
            observations=sanitize(observations, self.replacements),
        )
        print(f"{name}: HTTP {exchange.status}")

    def require_list(self, exchange: Exchange) -> list[dict]:
        if not exchange.ok or not isinstance(exchange.response_body, list):
            raise ProbeAborted(
                f"GET {exchange.path}: HTTP {exchange.status} {self.show(exchange.response_body)}"
            )
        return exchange.response_body

    def run(self) -> None:
        self.record_offers()
        domain_id = self.record_directory(
            "02-get-domains",
            "Список доменов (оставлен только наш домен)",
            self.call("GET", "/domains"),
            self.settings.campaign_domain,
            "Domain",
            foreign_fields=DOMAIN_FOREIGN_FIELDS,
        )
        group_id = self.record_directory(
            "03-get-campaign-groups",
            "Группы кампаний (оставлена только наша группа)",
            self.call("GET", "/groups", query={"type": "campaigns"}),
            self.settings.campaign_group,
            "Campaign group",
        )
        traffic_source_id = self.record_directory(
            "04-get-traffic-sources",
            "Источники трафика (оставлен только наш источник)",
            self.call("GET", "/traffic_sources"),
            self.settings.campaign_traffic_source,
            "Traffic source",
        )
        self.record_errors()

        campaign_body = {
            "name": f"{self.prefix}put_check",
            "alias": random_alias(),
            "type": "position",
            "state": "active",
            "domain_id": domain_id,
            "group_id": group_id,
            "traffic_source_id": traffic_source_id,
        }
        campaign_id = self.create(
            "10-create-campaign", "Создание кампании", "/campaigns", campaign_body, "campaign"
        )
        self.record_alias_conflict(campaign_body)

        country_flow_id = self.create(
            "12-create-stream-country-redirect",
            "Создание потока: страна → редирект",
            "/streams",
            {
                "campaign_id": campaign_id,
                "name": "Flow 1",
                "type": "regular",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": self.settings.redirect_url,
                "filters": [{"name": "country", "mode": "accept", "payload": [TEST_COUNTRY]}],
                "state": "active",
            },
            "stream",
        )
        self.create(
            "13-create-stream-offers",
            "Создание потока: все остальные → оффер",
            "/streams",
            self.offers_stream_body(campaign_id, "Flow 2", position=2),
            "stream",
        )
        probe_stream_body = self.offers_stream_body(campaign_id, "Probe", position=3)
        probe_stream_body["comments"] = "probe"
        probe_stream_body["filters"] = [
            {"name": "country", "mode": "reject", "payload": [PROBE_REJECTED_COUNTRY]}
        ]
        probe_stream_id = self.create(
            "14-create-stream-probe",
            "Создание потока с фильтром, комментарием и оффером (для проверки PUT)",
            "/streams",
            probe_stream_body,
            "stream",
        )
        self.record(
            "15-get-campaign-streams",
            "Потоки кампании",
            self.call("GET", f"/campaigns/{campaign_id}/streams"),
        )

        offers_only = self.put_offers(
            "16-put-stream-offers-only",
            "PUT потока только с офферами",
            probe_stream_id,
            [self.stream_offer(share=100)],
        )
        # Keitaro turns the unused action_payload of a landings stream from null into "" when the
        # stream is saved (docs/decisions.md, В3); file 16 keeps the raw diff as evidence.
        unexpected_changes = {
            field: values
            for field, values in offers_only.changes.items()
            if not (field == "action_payload" and set(values) <= {None, ""})
        }
        if not offers_only.put.ok or unexpected_changes:
            self.stop_conditions.append("16: PUT with only offers rejected or changed other fields")
        self.put_offers(
            "17-put-stream-offers-share-zero",
            "PUT потока: оффер с весом 0",
            probe_stream_id,
            [self.stream_offer(share=0)],
        )
        emptied = self.put_offers(
            "18-put-stream-offers-empty",
            "PUT потока: пустой список офферов",
            probe_stream_id,
            [],
        )
        if offer_rows(emptied.after):
            self.stop_conditions.append("18: offers left in the stream after PUT offers=[]")
        self.put_offers(
            "19-put-stream-offers-restore",
            "PUT потока: возврат оффера",
            probe_stream_id,
            [self.stream_offer(share=100)],
        )

        self.record_campaign_list(campaign_id)
        self.record_stream_archive(probe_stream_id)
        self.record_campaign_archive(campaign_id, country_flow_id)

    def record_offers(self) -> None:
        exchange = self.call("GET", "/offers")
        ours = keep_only_ids(self.require_list(exchange), {PROBE_OFFER_ID})
        if not ours:
            raise ProbeAborted(f"Offer {PROBE_OFFER_ID} is not visible through the API")
        ours = redact_fields(ours, OFFER_OWNER_FIELDS)
        self.record(
            "01-get-offers",
            "Список офферов (оставлен только наш оффер, данные владельца скрыты)",
            replace(exchange, response_body=ours),
        )

    def record_directory(
        self,
        name: str,
        title: str,
        exchange: Exchange,
        configured: str,
        what: str,
        *,
        foreign_fields: Collection[str] = (),
    ) -> int:
        identifier = find_configured(self.require_list(exchange), configured, what)
        ours = redact_fields(keep_only_ids(exchange.response_body, {identifier}), foreign_fields)
        self.record(name, title, replace(exchange, response_body=ours))
        return identifier

    def record_errors(self) -> None:
        with make_client(self.settings, INVALID_API_KEY) as invalid_key_client:
            self.record(
                "05-error-invalid-api-key",
                "GET /offers с неверным ключом API",
                call(invalid_key_client, "GET", "/offers"),
            )
        self.record(
            "06-error-not-found",
            "GET несуществующей кампании",
            self.call("GET", f"/campaigns/{NOT_FOUND_CAMPAIGN_ID}"),
        )

    def create(self, name: str, title: str, path: str, body: dict, kind: str) -> int:
        exchange = self.call("POST", path, body=body)
        if kind == "campaign":
            self.hide_campaign_token(exchange.response_body)
        self.record(name, title, exchange)
        response_body = exchange.response_body
        if not exchange.ok or not isinstance(response_body, dict) or "id" not in response_body:
            raise ProbeAborted(
                f"{name}: Keitaro rejected the body: HTTP {exchange.status} "
                f"{self.show(response_body)}"
            )
        identifier = int(response_body["id"])
        registry = self.created.campaign_ids if kind == "campaign" else self.created.stream_ids
        registry.append(identifier)
        return identifier

    def hide_campaign_token(self, campaign: Any) -> None:
        # The token lets anyone who knows the tracker send clicks to the campaign (Click API);
        # registered before recording, so this and every later example shows "***".
        if isinstance(campaign, dict) and isinstance(campaign.get("token"), str):
            self.replacements[campaign["token"]] = "***"

    def record_alias_conflict(self, campaign_body: dict) -> None:
        conflict = self.call(
            "POST", "/campaigns", body={**campaign_body, "name": f"{self.prefix}alias_conflict"}
        )
        observations = {}
        duplicate = conflict.response_body
        self.hide_campaign_token(duplicate)
        if conflict.ok and isinstance(duplicate, dict) and "id" in duplicate:
            # A duplicate was accepted: it is ours, so archive it right away.
            duplicate_id = int(duplicate["id"])
            self.created.campaign_ids.append(duplicate_id)
            archived = self.call("DELETE", f"/campaigns/{duplicate_id}")
            observations["duplicate_archived"] = {
                "status": archived.status,
                "body": archived.response_body,
            }
        self.record(
            "11-create-campaign-alias-taken",
            "Создание кампании с уже занятым alias",
            conflict,
            observations,
        )

    def offers_stream_body(self, campaign_id: int, name: str, *, position: int) -> dict:
        return {
            "campaign_id": campaign_id,
            "name": name,
            "type": "regular",
            "position": position,
            "schema": "landings",
            "action_type": "http",
            "offers": [self.stream_offer(share=100)],
            "state": "active",
        }

    @staticmethod
    def stream_offer(*, share: int) -> dict:
        return {"offer_id": PROBE_OFFER_ID, "share": share, "state": "active"}

    def put_offers(self, name: str, title: str, stream_id: int, offers: list[dict]) -> PutResult:
        path = f"/streams/{stream_id}"
        before_read = self.call("GET", path)
        put = self.call("PUT", path, body={"offers": offers})
        after_read = self.call("GET", path)
        before, after = before_read.response_body, after_read.response_body
        changes = {}
        unreadable = [
            f"GET {moment} PUT: HTTP {read.status}"
            for moment, read in (("before", before_read), ("after", after_read))
            if not read.ok or not isinstance(read.response_body, dict)
        ]
        if unreadable:
            # Without both snapshots the PUT cannot be judged; empty changes would pass as success.
            self.stop_conditions.append(f"{name}: stream unreadable ({'; '.join(unreadable)})")
        else:
            changes = changed_fields(before, after, ignore=STREAM_FIELDS_ALLOWED_TO_CHANGE)
        self.record(
            name,
            title,
            put,
            {"stream_before": before, "stream_after": after, "changed_fields": changes},
        )
        print(f"  changed_fields: {self.show(changes)}")
        print(f"  offers before: {self.show(offer_rows(before))}")
        print(f"  offers after:  {self.show(offer_rows(after))}")
        return PutResult(put, after, changes)

    def record_campaign_list(self, campaign_id: int) -> None:
        exchange = self.call("GET", "/campaigns")
        campaigns = self.require_list(exchange)
        self.record(
            "20-get-campaigns",
            "Список кампаний (оставлена только наша кампания)",
            replace(exchange, response_body=keep_only_ids(campaigns, {campaign_id})),
            {"total_count": len(campaigns)},
        )

    def snapshot(self, path: str) -> dict:
        exchange = self.call("GET", path)
        return {"status": exchange.status, "body": exchange.response_body}

    def record_stream_archive(self, stream_id: int) -> None:
        exchange = self.call("DELETE", f"/streams/{stream_id}")
        self.record(
            "21-delete-stream",
            "Удаление (архивирование) потока",
            exchange,
            {"stream_after": self.snapshot(f"/streams/{stream_id}")},
        )

    def record_campaign_archive(self, campaign_id: int, country_flow_id: int) -> None:
        # Its flows are deliberately left live: does archiving a campaign archive them too?
        exchange = self.call("DELETE", f"/campaigns/{campaign_id}")
        self.record(
            "22-delete-campaign",
            "Удаление (архивирование) кампании с живыми потоками",
            exchange,
            {
                "campaign_after": self.snapshot(f"/campaigns/{campaign_id}"),
                "country_flow_after": self.snapshot(f"/streams/{country_flow_id}"),
                "campaign_streams_after": self.snapshot(f"/campaigns/{campaign_id}/streams"),
            },
        )

    def archive_status(self, kind: str, identifier: int) -> tuple[bool, str]:
        """Whether Keitaro shows our object as archived, plus its answer for the final check."""
        try:
            exchange = self.call("GET", f"/{kind}/{identifier}")
        except httpx.HTTPError as error:
            # Unknown counts as live: cleanup then tries to archive it once more.
            return False, type(error).__name__
        body = exchange.response_body
        state = body.get("state") if isinstance(body, dict) else None
        # An archived campaign answers 404, an archived stream stays readable (files 21, 22).
        archived = exchange.status == 404 or (exchange.ok and state == "deleted")
        return archived, f"status={exchange.status} state={state}"

    def cleanup(self) -> bool:
        """Archives whatever this run created and Keitaro still shows as live; True if all clean."""
        live = CreatedObjects(
            campaign_ids=[
                identifier
                for identifier in self.created.campaign_ids
                if not self.archive_status("campaigns", identifier)[0]
            ],
            stream_ids=[
                identifier
                for identifier in self.created.stream_ids
                if not self.archive_status("streams", identifier)[0]
            ],
        )
        print(
            f"cleanup: archiving {len(live.stream_ids)} live streams, "
            f"{len(live.campaign_ids)} live campaigns"
        )
        errors = live.archive_all(self.client)
        for error in errors:
            print(f"cleanup error: {sanitize(error, self.replacements)}")

        all_archived = True
        for kind, identifiers in (
            ("streams", self.created.stream_ids),
            ("campaigns", self.created.campaign_ids),
        ):
            for identifier in identifiers:
                archived, answer = self.archive_status(kind, identifier)
                print(f"final check: {kind}/{identifier} {answer}")
                all_archived &= archived
        return not errors and all_archived


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--confirm-writes",
        action="store_true",
        help="required: the probe creates, changes and archives objects in the real Keitaro",
    )
    arguments = parser.parse_args(argv)
    if not arguments.confirm_writes:
        print("Refusing to run: it writes to the real Keitaro, pass --confirm-writes.")
        return 2
    settings = Settings()
    if not settings.keitaro_write_name_prefix:
        # Without a prefix our test objects would look like any other user's campaigns.
        print("Refusing to run: KEITARO_WRITE_NAME_PREFIX is empty.")
        return 2

    succeeded = False
    with make_client(settings, settings.keitaro_api_key.get_secret_value()) as client:
        probe = KeitaroProbe(settings, client)
        try:
            probe.run()
            succeeded = True
        except ProbeAborted as error:
            print(f"ABORTED: {error}")
        except httpx.HTTPError as error:
            # The exception text may contain the tracker address.
            print(f"ABORTED: Keitaro request failed: {type(error).__name__}")
        finally:
            cleaned = probe.cleanup()

    for condition in probe.stop_conditions:
        print(f"STOP CONDITION: {condition}")
    return 0 if succeeded and cleaned and not probe.stop_conditions else 1


if __name__ == "__main__":
    sys.exit(main())
