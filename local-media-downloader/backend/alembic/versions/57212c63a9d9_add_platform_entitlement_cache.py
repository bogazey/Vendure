"""add platform_entitlement_cache for bounded entitlement-availability fallback

Revision ID: 57212c63a9d9
Revises: 9c3d7f1a4e56
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.database.sa_types


# revision identifiers, used by Alembic.
revision: str = '57212c63a9d9'
down_revision: Union[str, None] = '9c3d7f1a4e56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'platform_entitlement_cache',
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=40), nullable=False),
        sa.Column('entitled', sa.Boolean(), nullable=False),
        sa.Column('plan_slug', sa.String(length=80), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('entitlement_expires_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=True),
        sa.Column('checked_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id', 'product_id'),
    )


def downgrade() -> None:
    op.drop_table('platform_entitlement_cache')
