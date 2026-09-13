"""add last_status_check_at to platform_oidc_tokens for bounded central session revocation

Revision ID: a13f8e2c6b47
Revises: 57212c63a9d9
Create Date: 2026-09-13 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.database.sa_types


# revision identifiers, used by Alembic.
revision: str = 'a13f8e2c6b47'
down_revision: Union[str, None] = '57212c63a9d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'platform_oidc_tokens',
        sa.Column('last_status_check_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('platform_oidc_tokens', 'last_status_check_at')
