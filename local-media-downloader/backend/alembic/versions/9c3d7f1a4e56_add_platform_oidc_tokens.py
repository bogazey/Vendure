"""add platform_oidc_tokens for central identity entitlement retrieval

Revision ID: 9c3d7f1a4e56
Revises: 8a1e5c3f9b02
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.database.sa_types


# revision identifiers, used by Alembic.
revision: str = '9c3d7f1a4e56'
down_revision: Union[str, None] = '8a1e5c3f9b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'platform_oidc_tokens',
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('refresh_token', sa.String(length=500), nullable=False),
        sa.Column('access_token', sa.String(length=2000), nullable=True),
        sa.Column('access_token_expires_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=True),
        sa.Column('updated_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('platform_oidc_tokens')
