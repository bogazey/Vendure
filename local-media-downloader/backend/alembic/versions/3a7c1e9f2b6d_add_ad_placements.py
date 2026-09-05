"""add ad_placements table

Revision ID: 3a7c1e9f2b6d
Revises: 224af020fc5a
Create Date: 2026-09-05 22:00:00.000000

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database.sa_types


# revision identifiers, used by Alembic.
revision: str = '3a7c1e9f2b6d'
down_revision: Union[str, None] = '224af020fc5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ad_placements_table = sa.table(
    'ad_placements',
    sa.column('id', sa.String),
    sa.column('description', sa.String),
    sa.column('enabled', sa.Boolean),
    sa.column('provider', sa.String),
    sa.column('public_slot_id', sa.String),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
)

# Seeded disabled (no provider configured yet) - this is infrastructure/
# control only, see COMMERCIAL_ARCHITECTURE.md. An admin opts a placement in
# from /admin/ads once a real ad network is ready.
SEED_PLACEMENTS = [
    {
        "id": "LANDING_DOWNLOADER",
        "description": "Below the URL input on the marketing landing page downloader.",
    },
    {
        "id": "DOWNLOAD_RESULT",
        "description": "Alongside a completed download's result card.",
    },
    {
        "id": "USER_DASHBOARD",
        "description": "In the authenticated dashboard, away from download controls.",
    },
    {
        "id": "DOWNLOAD_HISTORY",
        "description": "Within the download history / media library list.",
    },
]


def upgrade() -> None:
    op.create_table(
        'ad_placements',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('description', sa.String(length=240), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('provider', sa.String(length=80), nullable=True),
        sa.Column('public_slot_id', sa.String(length=120), nullable=True),
        sa.Column('created_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=False),
        sa.Column('updated_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        ad_placements_table,
        [
            {
                "id": placement["id"],
                "description": placement["description"],
                "enabled": False,
                "provider": None,
                "public_slot_id": None,
                "created_at": now,
                "updated_at": now,
            }
            for placement in SEED_PLACEMENTS
        ],
    )


def downgrade() -> None:
    op.drop_table('ad_placements')
