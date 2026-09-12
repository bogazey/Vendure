"""add gifted subscription fields

Revision ID: 7d2e9a4c1f83
Revises: 4c8a1f2e6b9d
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d2e9a4c1f83'
down_revision: Union[str, None] = '4c8a1f2e6b9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Both columns are nullable and unpopulated for every existing row -
    # existing Paddle subscriptions keep provider="paddle" (unchanged) with
    # both new columns null, and existing Free accounts have no
    # subscription row at all, so nothing is reclassified as gifted.
    # batch_alter_table (not a plain op.add_column with an inline
    # ForeignKey) because SQLite can't ALTER a table to add a new FK
    # constraint directly - see 224af020fc5a for the same pattern.
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('granted_by_admin_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('granted_reason', sa.String(length=500), nullable=True))
        batch_op.create_foreign_key(
            'fk_subscriptions_granted_by_admin_id', 'users', ['granted_by_admin_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_subscriptions_granted_by_admin_id', type_='foreignkey')
        batch_op.drop_column('granted_reason')
        batch_op.drop_column('granted_by_admin_id')
