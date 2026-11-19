from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CreatedCampaign, CreationStatus


class CreatedCampaignsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_pending(self, name: str, country: str, offer_id: int) -> CreatedCampaign:
        # Committed immediately: the trace must survive even if the process dies mid-creation.
        now = datetime.now(UTC)
        entry = CreatedCampaign(
            name=name,
            country=country,
            offer_id=offer_id,
            status=CreationStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._session.add(entry)
        self._session.commit()
        return entry

    def save(self, entry: CreatedCampaign) -> None:
        entry.updated_at = datetime.now(UTC)
        self._session.add(entry)
        self._session.commit()

    def list_recent(self, limit: int = 100) -> list[CreatedCampaign]:
        query = select(CreatedCampaign).order_by(CreatedCampaign.id.desc()).limit(limit)
        return list(self._session.scalars(query))
