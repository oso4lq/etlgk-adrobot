"""Journal of campaigns created by the app.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "created_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("alias", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("keitaro_campaign_id", sa.Integer(), nullable=True),
        sa.Column("country_stream_id", sa.Integer(), nullable=True),
        sa.Column("offers_stream_id", sa.Integer(), nullable=True),
        sa.Column("campaign_url", sa.String(length=1024), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_created_campaigns")),
    )


def downgrade() -> None:
    op.drop_table("created_campaigns")
