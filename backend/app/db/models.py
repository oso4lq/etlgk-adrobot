from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.db.base import Base


class UtcDateTime(TypeDecorator):
    """Stores UTC and always returns timezone-aware UTC datetimes.

    SQLite drops tzinfo on read even for DateTime(timezone=True), so without this the same
    column would be aware right after creation and naive after a reload.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UtcDateTime requires a timezone-aware datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class CreationStatus(StrEnum):
    PENDING = "pending"
    CREATED = "created"
    FAILED = "failed"
    COMPENSATION_FAILED = "compensation_failed"


class CreatedCampaign(Base):
    """Journal entry for one campaign creation attempt, written before Keitaro is touched."""

    __tablename__ = "created_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(2))
    offer_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    keitaro_campaign_id: Mapped[int | None] = mapped_column(Integer)
    country_stream_id: Mapped[int | None] = mapped_column(Integer)
    offers_stream_id: Mapped[int | None] = mapped_column(Integer)
    campaign_url: Mapped[str | None] = mapped_column(String(1024))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())
