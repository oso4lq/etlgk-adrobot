from app.core.errors import AppError


class CampaignNotFetchedError(AppError):
    code = "campaign_not_fetched"
    http_status = 404

    def __init__(self, keitaro_campaign_id: int) -> None:
        super().__init__(
            f"Кампания {keitaro_campaign_id} ещё не загружена в редактор — выполните Fetch Streams"
        )
