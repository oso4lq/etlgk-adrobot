"""One test per step of the video (docs/video-transcript.md), asserting what the screen shows.

Every test replays the previous steps through the helpers below, so each one reads as
"the state after step N" and a failure points at the step that diverges from the video.
"""

import pytest

from app.services.campaign_fetcher import CampaignFetcher
from app.services.editor_views import stream_response
from app.services.stream_editor import StreamEditor
from app.services.stream_publisher import StreamPublisher

PREFIX = "test_oso4lq_"


class Video:
    """The wrapper as the user drives it: the same calls the API endpoints make."""

    def __init__(self, fake, editor_repository, db_session, offer_catalog, make_settings):
        self.fake = fake
        self.repository = editor_repository
        self.db_session = db_session
        self.fetcher = CampaignFetcher(fake, offer_catalog)
        self.editor = StreamEditor(offer_catalog)
        self.publisher = StreamPublisher(fake, make_settings(keitaro_write_name_prefix=PREFIX))
        for offer_id in range(1001, 1006):
            fake.add_offer(offer_id, f"Offer {offer_id}")
        self.campaign = fake.add_campaign(f"{PREFIX}video")
        self.flow_one = fake.add_stream(self.campaign.id, "Flow 1", 1)
        self.flow_two = fake.add_stream(
            self.campaign.id, "Flow 2", 2, [(1001, 34), (1002, 33), (1003, 33)]
        )

    def fetch(self):
        return self.fetcher.fetch(self.repository, self.campaign.id)

    def screen(self, stream_id):
        self.db_session.expire_all()
        return stream_response(self.repository.find_stream(stream_id), PREFIX)

    def flow_two_screen(self):
        return self.screen(self.flow_two.id)

    def flow_two_offers(self):
        return [
            (o.offer_id, o.status, o.weight, o.is_pinned) for o in self.flow_two_screen().offers
        ]

    def keitaro_flow_two(self):
        return [(o.offer_id, o.share) for o in self.fake.streams[self.flow_two.id].offers]

    def add(self, offer_id):
        self.editor.add_offer(self.repository, self.flow_two.id, offer_id)

    def remove(self, offer_id):
        self.editor.remove_offer(self.repository, self.flow_two.id, offer_id)

    def bring_back(self, offer_id):
        self.editor.bring_back_offer(self.repository, self.flow_two.id, offer_id)

    def pin(self, offer_id):
        self.editor.pin_offer(self.repository, self.flow_two.id, offer_id)

    def cancel(self):
        self.editor.cancel(self.repository, self.flow_two.id)

    def push(self):
        self.publisher.push(self.repository, self.flow_two.id)


@pytest.fixture
def video(fake, editor_repository, db_session, offer_catalog, make_settings) -> Video:
    return Video(fake, editor_repository, db_session, offer_catalog, make_settings)


def after_step_1(video):
    video.fetch()


def after_step_3(video):
    after_step_1(video)
    video.add(1004)
    video.push()


def after_step_5(video):
    after_step_3(video)
    video.remove(1002)
    video.push()


def after_step_6(video):
    after_step_5(video)
    video.bring_back(1002)
    video.push()


def after_step_7(video):
    after_step_6(video)
    video.fake.set_stream_offers(video.flow_two.id, [(1001, 25), (1002, 25)])
    video.fetch()


def test_step_1_fetch_streams_shows_offers_and_plain_stream(video):
    after_step_1(video)
    plain = video.screen(video.flow_one.id)
    # Pins: a stream without offers is shown as a plain stream, no offers, nothing to push.
    assert (plain.has_offers, plain.offers, plain.is_draft, plain.can_push) == (
        False,
        [],
        False,
        False,
    )
    screen = video.flow_two_screen()
    # Pins: the offers come with Keitaro's weights and the stream is white.
    assert video.flow_two_offers() == [
        (1001, "active", 34, False),
        (1002, "active", 33, False),
        (1003, "active", 33, False),
    ]
    assert not screen.is_draft


def test_step_2_added_offer_gives_25_each_and_yellow_but_keitaro_has_three(video):
    after_step_1(video)
    video.add(1004)
    screen = video.flow_two_screen()
    # Pins: after adding, weights are recalculated to 25 each and the stream turns yellow.
    assert video.flow_two_offers() == [
        (1001, "active", 25, False),
        (1002, "active", 25, False),
        (1003, "active", 25, False),
        (1004, "active", 25, False),
    ]
    assert screen.is_draft
    # Pins: Keitaro is untouched until Push.
    assert video.keitaro_flow_two() == [(1001, 34), (1002, 33), (1003, 33)]


def test_step_3_push_sends_four_offers_and_stream_turns_white(video):
    after_step_3(video)
    assert video.keitaro_flow_two() == [(1001, 25), (1002, 25), (1003, 25), (1004, 25)]
    # Pins: after publishing the stream is white again.
    assert not video.flow_two_screen().is_draft
    assert sum(weight for _, _, weight, _ in video.flow_two_offers()) == 100


def test_step_4_cancel_drops_unpublished_offer_and_stream_turns_white(video):
    after_step_3(video)
    video.add(1005)
    assert video.flow_two_screen().is_draft
    video.cancel()
    screen = video.flow_two_screen()
    # Pins: the unpublished binding is deleted and the stream is white again.
    assert [offer_id for offer_id, *_ in video.flow_two_offers()] == [1001, 1002, 1003, 1004]
    assert not screen.is_draft
    assert video.keitaro_flow_two() == [(1001, 25), (1002, 25), (1003, 25), (1004, 25)]
    # Pins: only the binding is removed, the offer itself still exists.
    assert 1005 in [offer.id for offer in video.fake.offers]


def test_step_5_removed_offer_is_grey_zero_and_after_push_gone_from_keitaro_but_archived(video):
    after_step_3(video)
    video.remove(1002)
    screen = video.flow_two_screen()
    # Pins: removed offer is grey with 0%, the others are 34/33/33, the stream is yellow.
    assert video.flow_two_offers() == [
        (1001, "active", 34, False),
        (1002, "removed", 0, False),
        (1003, "active", 33, False),
        (1004, "active", 33, False),
    ]
    assert screen.is_draft
    video.push()
    # Pins: after publishing the offer is gone from Keitaro but stays grey in our archive.
    assert video.keitaro_flow_two() == [(1001, 34), (1003, 33), (1004, 33)]
    assert (1002, "removed", 0, False) in video.flow_two_offers()
    assert not video.flow_two_screen().is_draft


def test_step_6_bring_back_and_push_returns_offer_to_keitaro(video):
    after_step_5(video)
    video.bring_back(1002)
    screen = video.flow_two_screen()
    # Pins: bring back makes the stream yellow and recalculates to 25 x 4.
    assert video.flow_two_offers() == [
        (1001, "active", 25, False),
        (1002, "active", 25, False),
        (1003, "active", 25, False),
        (1004, "active", 25, False),
    ]
    assert screen.is_draft
    video.push()
    assert video.keitaro_flow_two() == [(1001, 25), (1002, 25), (1003, 25), (1004, 25)]
    assert not video.flow_two_screen().is_draft


def test_step_7_offers_deleted_in_keitaro_turn_grey_after_fetch(video):
    after_step_6(video)
    video.fake.set_stream_offers(video.flow_two.id, [(1001, 25), (1002, 25)])
    video.fetch()
    screen = video.flow_two_screen()
    # Pins: offers deleted by hand in Keitaro become removed with 0%, as if removed here.
    assert video.flow_two_offers() == [
        (1001, "active", 25, False),
        (1002, "active", 25, False),
        (1003, "removed", 0, False),
        (1004, "removed", 0, False),
    ]
    # Pins: the stream is white after such a Fetch.
    assert not screen.is_draft
    # Pins: Bring back is possible for the grey offer.
    video.bring_back(1003)
    assert video.flow_two_screen().is_draft
    video.cancel()
    assert video.flow_two_offers()[2] == (1003, "removed", 0, False)


def test_step_8_pinned_weight_survives_bring_back_and_push(video):
    after_step_7(video)
    video.pin(1001)
    video.bring_back(1003)
    screen = video.flow_two_screen()
    # Pins: pinned 25 stays, the remaining 75 is split between the unpinned active offers.
    assert video.flow_two_offers() == [
        (1001, "active", 25, True),
        (1002, "active", 38, False),
        (1003, "active", 37, False),
        (1004, "removed", 0, False),
    ]
    assert screen.is_draft
    video.push()
    assert video.keitaro_flow_two() == [(1001, 25), (1002, 38), (1003, 37)]
    assert not video.flow_two_screen().is_draft
