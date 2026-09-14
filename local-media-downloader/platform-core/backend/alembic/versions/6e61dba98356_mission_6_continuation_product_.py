"""mission 6 continuation: product description and discoverable flag

Revision ID: 6e61dba98356
Revises: 76e4bdbdea17
Create Date: 2026-09-14 14:53:02.567992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.database.sa_types


# revision identifiers, used by Alembic.
revision: str = '6e61dba98356'
down_revision: Union[str, None] = '76e4bdbdea17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('description', sa.String(length=500), nullable=True))
    # NOT NULL with a server_default so existing rows backfill to
    # discoverable=true (the pre-existing behavior every product already
    # had implicitly), then the default is dropped so future inserts must
    # supply it explicitly (mirrors the `plans` NOT-NULL-column pattern
    # from the earlier Mission 6 continuation migration).
    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(sa.Column('is_discoverable', sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table('products') as batch_op:
        batch_op.alter_column('is_discoverable', server_default=None)


def downgrade() -> None:
    op.drop_column('products', 'is_discoverable')
    op.drop_column('products', 'description')
