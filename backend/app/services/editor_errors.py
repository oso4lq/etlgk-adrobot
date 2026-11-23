from app.core.errors import AppError


class CampaignNotFetchedError(AppError):
    code = "campaign_not_fetched"
    http_status = 404

    def __init__(self, keitaro_campaign_id: int) -> None:
        super().__init__(
            f"Кампания {keitaro_campaign_id} ещё не загружена в редактор — выполните Fetch Streams"
        )


class StreamNotFoundError(AppError):
    code = "stream_not_found"
    http_status = 404

    def __init__(self, keitaro_stream_id: int) -> None:
        super().__init__(
            f"Поток {keitaro_stream_id} не найден в редакторе — выполните Fetch Streams"
        )


class OfferNotInStreamError(AppError):
    code = "offer_not_in_stream"
    http_status = 404

    def __init__(self, offer_id: int, keitaro_stream_id: int) -> None:
        super().__init__(f"Оффера {offer_id} нет в потоке {keitaro_stream_id}")


class StreamWithoutOffersError(AppError):
    code = "stream_without_offers"
    http_status = 422

    def __init__(self, keitaro_stream_id: int) -> None:
        super().__init__(
            f"Поток {keitaro_stream_id} без офферов: "
            "добавлять офферы можно только в потоки, где они уже есть"
        )


class OfferAlreadyInStreamError(AppError):
    code = "offer_already_in_stream"
    http_status = 409

    def __init__(self, offer_id: int) -> None:
        super().__init__(f"Оффер {offer_id} уже есть в потоке")
