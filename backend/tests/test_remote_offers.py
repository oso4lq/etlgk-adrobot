from app.domain.offer_sync import RemoteOffer
from app.services.remote_offers import remote_offers


def test_remote_offers_reads_active_disabled_and_duplicate_rows(fake):
    campaign = fake.add_campaign("test_oso4lq_remote")
    stream = fake.add_stream(
        campaign.id,
        "Flow",
        1,
        [(1001, 30), (1002, 20, "disabled"), (1001, 20), (1003, 30)],
    )
    assert remote_offers(stream) == [
        RemoteOffer(1001, 50, True),
        RemoteOffer(1002, 0, False),
        RemoteOffer(1003, 30, True),
    ]
