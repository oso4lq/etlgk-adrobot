import json

import httpx
import pytest

from app.keitaro.client import KeitaroHttpClient
from app.keitaro.errors import (
    KeitaroAliasTakenError,
    KeitaroRejectedError,
    KeitaroUnavailableError,
)
from app.keitaro.http_session import KeitaroHttpSession
from app.keitaro.models import (
    KeitaroCampaign,
    NewCampaign,
    NewCountryRedirectStream,
    NewOffersStream,
    StreamOfferShare,
)


def client_answering(status: int, body, sent: list[httpx.Request]) -> KeitaroHttpClient:
    """Replays a recorded Keitaro response and remembers what our client sent."""

    def handler(request):
        sent.append(request)
        return httpx.Response(status, json=body)

    session = KeitaroHttpSession(
        "https://tracker.example.com",
        "test-key",
        timeout_seconds=5,
        max_retries=0,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    return KeitaroHttpClient(session)


def replay(example: dict, sent: list[httpx.Request]) -> KeitaroHttpClient:
    return client_answering(example["response"]["status"], example["response"]["body"], sent)


def test_list_offers_parses_real_example(keitaro_example):
    sent = []
    offers = replay(keitaro_example("01-get-offers"), sent).list_offers()
    assert [offer.id for offer in offers] == [18813]
    assert (sent[0].method, sent[0].url.path) == ("GET", "/admin_api/v1/offers")


def test_list_domains_parses_real_example(keitaro_example):
    domains = replay(keitaro_example("02-get-domains"), []).list_domains()
    assert [(domain.id, domain.name) for domain in domains] == [(1813, "kylovoa.com")]


def test_list_campaign_groups_asks_for_campaign_type(keitaro_example):
    sent = []
    groups = replay(keitaro_example("03-get-campaign-groups"), sent).list_campaign_groups()
    assert [(group.id, group.name) for group in groups] == [(10332, "FORTESTS")]
    assert sent[0].url.params["type"] == "campaigns"


def test_list_traffic_sources_parses_real_example(keitaro_example):
    sources = replay(keitaro_example("04-get-traffic-sources"), []).list_traffic_sources()
    assert [(source.id, source.name) for source in sources] == [(836, "FORTESTS")]


def test_create_campaign_sends_verified_body(keitaro_example):
    example = keitaro_example("24-create-campaign-admin-defaults")
    body = example["request"]["body"]
    sent = []
    campaign = replay(example, sent).create_campaign(
        NewCampaign(
            name=body["name"],
            alias=body["alias"],
            domain_id=body["domain_id"],
            group_id=body["group_id"],
            traffic_source_id=body["traffic_source_id"],
        )
    )
    assert (sent[0].method, sent[0].url.path) == ("POST", "/admin_api/v1/campaigns")
    assert json.loads(sent[0].content) == body
    assert (campaign.id, campaign.alias) == (example["response"]["body"]["id"], body["alias"])


def test_create_country_redirect_stream_sends_verified_body(keitaro_example):
    example = keitaro_example("24-create-campaign-admin-defaults")
    body = example["observations"]["stream_bodies"][0]
    sent = []
    stream = client_answering(
        200, example["observations"]["streams_after"][0], sent
    ).create_country_redirect_stream(
        NewCountryRedirectStream(
            campaign_id=body["campaign_id"],
            name="Flow 1",
            position=1,
            country_code="DE",
            redirect_url=body["action_payload"],
        )
    )
    assert (sent[0].method, sent[0].url.path) == ("POST", "/admin_api/v1/streams")
    assert json.loads(sent[0].content) == body
    assert stream.id == example["observations"]["streams_after"][0]["id"]


def test_create_offers_stream_sends_verified_body(keitaro_example):
    example = keitaro_example("24-create-campaign-admin-defaults")
    body = example["observations"]["stream_bodies"][1]
    sent = []
    stream = client_answering(
        200, example["observations"]["streams_after"][1], sent
    ).create_offers_stream(
        NewOffersStream(
            campaign_id=body["campaign_id"],
            name="Flow 2",
            position=2,
            offers=(StreamOfferShare(offer_id=18813, share=100),),
        )
    )
    assert json.loads(sent[0].content) == body
    assert [(offer.offer_id, offer.share) for offer in stream.offers] == [(18813, 100)]


def test_get_campaign_streams_parses_real_example(keitaro_example):
    example = keitaro_example("15-get-campaign-streams")
    streams = replay(example, []).get_campaign_streams(campaign_id=1)
    by_name = {stream.name: stream for stream in streams}
    assert by_name["Flow 1"].flow_schema == "redirect" and by_name["Flow 1"].offers == []
    assert [(offer.offer_id, offer.share, offer.state) for offer in by_name["Flow 2"].offers] == [
        (18813, 100, "active")
    ]


def test_get_stream_parses_real_example(keitaro_example):
    stream_before = keitaro_example("16-put-stream-offers-only")["observations"]["stream_before"]
    stream = client_answering(200, stream_before, []).get_stream(stream_before["id"])
    assert stream.name == "Probe"


def test_replace_stream_offers_sends_only_offers(keitaro_example):
    example = keitaro_example("16-put-stream-offers-only")
    sent = []
    stream_id = example["observations"]["stream_before"]["id"]
    replay(example, sent).replace_stream_offers(stream_id, [StreamOfferShare(18813, 100)])
    assert (sent[0].method, sent[0].url.path) == ("PUT", f"/admin_api/v1/streams/{stream_id}")
    assert json.loads(sent[0].content) == example["request"]["body"]


def test_replace_stream_offers_with_empty_list(keitaro_example):
    example = keitaro_example("18-put-stream-offers-empty")
    sent = []
    replay(example, sent).replace_stream_offers(1, [])
    assert json.loads(sent[0].content) == {"offers": []}


def test_archive_stream_and_campaign_use_delete(keitaro_example):
    sent = []
    # Example 21 recorded a truly empty body, not a JSON string.
    empty_body_session = KeitaroHttpSession(
        "https://tracker.example.com",
        "test-key",
        timeout_seconds=5,
        max_retries=0,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(
            lambda request: sent.append(request) or httpx.Response(200, content=b"")
        ),
    )
    KeitaroHttpClient(empty_body_session).archive_stream(21)
    replay(keitaro_example("22-delete-campaign"), sent).archive_campaign(10)
    assert [(request.method, request.url.path) for request in sent] == [
        ("DELETE", "/admin_api/v1/streams/21"),
        ("DELETE", "/admin_api/v1/campaigns/10"),
    ]


def test_models_accept_nulls_and_numeric_strings():
    campaign = KeitaroCampaign.model_validate(
        {
            "id": "5",
            "name": "x",
            "alias": "a",
            "type": "position",
            "state": "active",
            "domain": None,
            "domain_id": None,
            "group_id": "10332",
            "traffic_source_id": None,
        }
    )
    assert (campaign.id, campaign.group_id, campaign.domain_id) == (5, 10332, None)


def test_alias_taken_raises_specific_error(keitaro_example):
    example = keitaro_example("11-create-campaign-alias-taken")
    body = example["request"]["body"]
    client = replay(example, [])
    with pytest.raises(KeitaroAliasTakenError) as error:
        client.create_campaign(
            NewCampaign(
                name=body["name"],
                alias=body["alias"],
                domain_id=body["domain_id"],
                group_id=body["group_id"],
                traffic_source_id=body["traffic_source_id"],
            )
        )
    assert "Alias has already used" in error.value.message
    assert error.value.keitaro_status == 422


def test_other_rejections_are_not_alias_taken():
    client = client_answering(422, {"name": ["Field is required"]}, [])
    with pytest.raises(KeitaroRejectedError) as error:
        client.create_campaign(NewCampaign("x", "a", 1, 2, 3))
    assert not isinstance(error.value, KeitaroAliasTakenError)


def test_list_campaigns_parses_real_example(keitaro_example):
    example = keitaro_example("20-get-campaigns")
    campaigns = replay(example, []).list_campaigns()
    assert campaigns[0].domain == example["response"]["body"][0]["domain"]


UNAVAILABLE_MESSAGE = "Keitaro недоступен: некорректный ответ"


def test_list_campaigns_skips_unparseable_items(caplog):
    good = {"id": 1, "name": "a", "alias": "x1", "type": "position", "state": "active"}
    bad = {"id": 2, "name": None, "alias": "x2", "type": "position", "state": "active"}
    client = client_answering(200, [good, bad, {**good, "id": 3}], [])
    assert [campaign.id for campaign in client.list_campaigns()] == [1, 3]
    assert "skipped 1" in caplog.text and "x2" not in caplog.text


def test_list_campaigns_non_list_body_is_unavailable():
    with pytest.raises(KeitaroUnavailableError, match=UNAVAILABLE_MESSAGE):
        client_answering(200, {"error": "x"}, []).list_campaigns()


def test_empty_body_is_reported_as_unavailable():
    session = KeitaroHttpSession(
        "https://tracker.example.com",
        "test-key",
        timeout_seconds=5,
        max_retries=0,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"")),
    )
    with pytest.raises(KeitaroUnavailableError, match=UNAVAILABLE_MESSAGE):
        KeitaroHttpClient(session).list_offers()


def test_unexpected_stream_shape_is_reported_as_unavailable():
    client = client_answering(200, [{"id": 1, "name": None}], [])
    with pytest.raises(KeitaroUnavailableError, match=UNAVAILABLE_MESSAGE):
        client.get_campaign_streams(10)


def test_unparseable_create_response_is_reported_as_unavailable():
    client = client_answering(200, {"unexpected": True}, [])
    campaign = NewCampaign(name="x", alias="a", domain_id=1, group_id=2, traffic_source_id=3)
    with pytest.raises(KeitaroUnavailableError, match=UNAVAILABLE_MESSAGE):
        client.create_campaign(campaign)
