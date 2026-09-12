"""add remember_me to refresh_tokens

Revision ID: 9f1c6a4e7d2b
Revises: 7b2e4f1a9c3d
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f1c6a4e7d2b'
down_revision: Union[str, None] = '7b2e4f1a9c3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'refresh_tokens',
        sa.Column('remember_me', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('refresh_tokens', 'remember_me')
