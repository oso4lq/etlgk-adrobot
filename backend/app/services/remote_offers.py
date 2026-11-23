from app.domain.offer_sync import RemoteOffer, merge_remote_offers
from app.keitaro.models import KeitaroStream


def remote_offers(stream: KeitaroStream) -> list[RemoteOffer]:
    """Offers of a Keitaro stream as the editor sees them.

    Fetch writes the published version from this reading and Push compares Keitaro
    against that version, so both must use this one function: if they read offers
    differently, Push would raise false conflicts or overwrite manual edits in Keitaro.
    """
    return merge_remote_offers(
        RemoteOffer(offer.offer_id, offer.share, offer.state == "active") for offer in stream.offers
    )
