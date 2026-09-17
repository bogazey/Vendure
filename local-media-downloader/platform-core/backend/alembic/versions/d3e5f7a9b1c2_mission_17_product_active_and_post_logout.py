"""mission 17: product is_active/updated_at + oauth client post_logout_redirect_uris

Revision ID: d3e5f7a9b1c2
Revises: c2d4e6f8a1b3
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e5f7a9b1c2'
down_revision: Union[str, None] = 'c2d4e6f8a1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                                       server_default=sa.func.now()))
    with op.batch_alter_table('oauth_clients') as batch_op:
        batch_op.add_column(sa.Column('post_logout_redirect_uris', sa.JSON(), nullable=False,
                                       server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('oauth_clients') as batch_op:
        batch_op.drop_column('post_logout_redirect_uris')
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('is_active')
