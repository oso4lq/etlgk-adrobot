from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EditorCampaign, EditorStream


class EditorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_campaign(self, keitaro_campaign_id: int) -> EditorCampaign | None:
        query = select(EditorCampaign).where(
            EditorCampaign.keitaro_campaign_id == keitaro_campaign_id
        )
        return self._session.scalars(query).one_or_none()

    def add_campaign(
        self, keitaro_campaign_id: int, name: str, fetched_at: datetime
    ) -> EditorCampaign:
        campaign = EditorCampaign(
            keitaro_campaign_id=keitaro_campaign_id, name=name, last_fetched_at=fetched_at
        )
        self._session.add(campaign)
        return campaign

    def find_stream(self, keitaro_stream_id: int) -> EditorStream | None:
        query = select(EditorStream).where(EditorStream.keitaro_stream_id == keitaro_stream_id)
        return self._session.scalars(query).one_or_none()

    def commit(self) -> None:
        try:
            self._session.commit()
        except Exception:
            # Without rollback the session stays unusable for the next operation.
            self._session.rollback()
            raise
