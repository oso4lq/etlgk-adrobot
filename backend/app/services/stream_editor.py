"""Local draft operations on one editor stream. Only our DB changes; Keitaro waits for Push."""

from collections.abc import Callable

from app.db.models import EditorStream, StreamOffer
from app.domain import offer_bindings
from app.domain.weights import OfferStatus
from app.repositories.editor import EditorRepository
from app.services.editor_errors import (
    OfferAlreadyInStreamError,
    OfferNotInStreamError,
    StreamNotFoundError,
    StreamWithoutOffersError,
)
from app.services.offer_catalog import OfferCatalog, OfferNotFoundError


class StreamEditor:
    def __init__(self, offer_catalog: OfferCatalog) -> None:
        self._offer_catalog = offer_catalog

    def add_offer(
        self, repository: EditorRepository, keitaro_stream_id: int, offer_id: int
    ) -> EditorStream:
        stream = self._load_stream(repository, keitaro_stream_id)
        if not stream.offers:
            raise StreamWithoutOffersError(keitaro_stream_id)

        existing = self._find_binding(stream, offer_id)
        if existing is not None:
            if existing.status == OfferStatus.ACTIVE:
                raise OfferAlreadyInStreamError(offer_id)
            offer_bindings.bring_back(stream.offers, existing)
            return self._commit(repository, stream)

        offer = self._offer_catalog.find(offer_id)
        if offer is None:
            raise OfferNotFoundError(offer_id)
        # Appended before recalculation so that the new binding takes part in it.
        stream.offers.append(
            StreamOffer(
                keitaro_offer_id=offer_id,
                offer_name=offer.name,
                sort_order=offer_bindings.next_sort_order(stream.offers),
                status=OfferStatus.ACTIVE,
                weight=0,
                is_pinned=False,
                published_status=None,
                published_weight=None,
            )
        )
        offer_bindings.recalculate(stream.offers)
        return self._commit(repository, stream)

    def remove_offer(
        self, repository: EditorRepository, keitaro_stream_id: int, offer_id: int
    ) -> EditorStream:
        return self._apply(repository, keitaro_stream_id, offer_id, offer_bindings.remove)

    def bring_back_offer(
        self, repository: EditorRepository, keitaro_stream_id: int, offer_id: int
    ) -> EditorStream:
        return self._apply(repository, keitaro_stream_id, offer_id, offer_bindings.bring_back)

    def pin_offer(
        self, repository: EditorRepository, keitaro_stream_id: int, offer_id: int
    ) -> EditorStream:
        return self._apply(repository, keitaro_stream_id, offer_id, offer_bindings.pin)

    def unpin_offer(
        self, repository: EditorRepository, keitaro_stream_id: int, offer_id: int
    ) -> EditorStream:
        return self._apply(repository, keitaro_stream_id, offer_id, offer_bindings.unpin)

    def cancel(self, repository: EditorRepository, keitaro_stream_id: int) -> EditorStream:
        stream = self._load_stream(repository, keitaro_stream_id)
        for unpublished in offer_bindings.cancel_draft(stream.offers):
            # delete-orphan removes the row; the offer itself stays in Keitaro.
            stream.offers.remove(unpublished)
        return self._commit(repository, stream)

    def _apply(
        self,
        repository: EditorRepository,
        keitaro_stream_id: int,
        offer_id: int,
        operation: Callable[[list[StreamOffer], StreamOffer], None],
    ) -> EditorStream:
        stream = self._load_stream(repository, keitaro_stream_id)
        operation(stream.offers, self._require_binding(stream, offer_id))
        return self._commit(repository, stream)

    @staticmethod
    def _load_stream(repository: EditorRepository, keitaro_stream_id: int) -> EditorStream:
        stream = repository.find_stream(keitaro_stream_id)
        if stream is None:
            raise StreamNotFoundError(keitaro_stream_id)
        return stream

    @staticmethod
    def _find_binding(stream: EditorStream, offer_id: int) -> StreamOffer | None:
        for binding in stream.offers:
            if binding.keitaro_offer_id == offer_id:
                return binding
        return None

    def _require_binding(self, stream: EditorStream, offer_id: int) -> StreamOffer:
        binding = self._find_binding(stream, offer_id)
        if binding is None:
            raise OfferNotInStreamError(offer_id, stream.keitaro_stream_id)
        return binding

    @staticmethod
    def _commit(repository: EditorRepository, stream: EditorStream) -> EditorStream:
        repository.commit()
        return stream
