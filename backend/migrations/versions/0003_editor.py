"""Editor: local copy of Keitaro streams and offer bindings.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "editor_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("keitaro_campaign_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_editor_campaigns")),
        sa.UniqueConstraint(
            "keitaro_campaign_id", name=op.f("uq_editor_campaigns_keitaro_campaign_id")
        ),
    )
    op.create_table(
        "editor_streams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("keitaro_stream_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["editor_campaigns.id"],
            name=op.f("fk_editor_streams_campaign_id_editor_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_editor_streams")),
        sa.UniqueConstraint("keitaro_stream_id", name=op.f("uq_editor_streams_keitaro_stream_id")),
    )
    op.create_table(
        "stream_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("keitaro_offer_id", sa.Integer(), nullable=False),
        sa.Column("offer_name", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("published_status", sa.String(length=16), nullable=True),
        sa.Column("published_weight", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["stream_id"],
            ["editor_streams.id"],
            name=op.f("fk_stream_offers_stream_id_editor_streams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stream_offers")),
        sa.UniqueConstraint(
            "stream_id", "keitaro_offer_id", name=op.f("uq_stream_offers_stream_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("stream_offers")
    op.drop_table("editor_streams")
    op.drop_table("editor_campaigns")
