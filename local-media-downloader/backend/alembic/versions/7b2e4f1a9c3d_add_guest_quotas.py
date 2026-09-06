"""add guest_quotas table

Revision ID: 7b2e4f1a9c3d
Revises: 3a7c1e9f2b6d
Create Date: 2026-09-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database.sa_types


# revision identifiers, used by Alembic.
revision: str = '7b2e4f1a9c3d'
down_revision: Union[str, None] = '3a7c1e9f2b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'guest_quotas',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('downloads_reserved', sa.Integer(), nullable=False),
        sa.Column('downloads_completed', sa.Integer(), nullable=False),
        sa.Column('created_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('guest_quotas')
