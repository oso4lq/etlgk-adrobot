from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
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


class EditorCampaign(Base):
    """Local copy of a Keitaro campaign the editor works with."""

    __tablename__ = "editor_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(Integer, unique=True)
    # Text, not String(255): the length of names coming from Keitaro is unknown.
    name: Mapped[str] = mapped_column(Text)
    last_fetched_at: Mapped[datetime] = mapped_column(UtcDateTime())

    streams: Mapped[list["EditorStream"]] = relationship(
        back_populates="campaign",
        order_by="EditorStream.position",
        cascade="all, delete-orphan",
    )


class EditorStream(Base):
    __tablename__ = "editor_streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("editor_campaigns.id", ondelete="CASCADE"))
    keitaro_stream_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)

    campaign: Mapped[EditorCampaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream",
        order_by="StreamOffer.sort_order",
        cascade="all, delete-orphan",
    )


class StreamOffer(Base):
    """Binding of a Keitaro offer to a stream: working version plus the published one."""

    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "keitaro_offer_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("editor_streams.id", ondelete="CASCADE"))
    keitaro_offer_id: Mapped[int] = mapped_column(Integer)
    offer_name: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    weight: Mapped[int] = mapped_column(Integer)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    published_status: Mapped[str | None] = mapped_column(String(16))
    published_weight: Mapped[int | None] = mapped_column(Integer)

    stream: Mapped[EditorStream] = relationship(back_populates="offers")
