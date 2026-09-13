"""add global_user_id for platform core identity migration

Revision ID: 8a1e5c3f9b02
Revises: 7d2e9a4c1f83
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a1e5c3f9b02'
down_revision: Union[str, None] = '7d2e9a4c1f83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable and unpopulated for every existing row - Loady's own `id`
    # remains the authoritative primary key for every existing foreign key
    # (history, usage_periods, usage_events, analytics_events, subscriptions)
    # and is never replaced. `global_user_id` is purely additive: it holds
    # the Platform Core identity a user has been linked to, once (and if)
    # the Loady->Platform-Core migration links or creates that account -
    # see docs/platform/LOADY_MIGRATION_DRY_RUN.md. A NULL value means
    # "not yet migrated/linked", not an error state.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('global_user_id', sa.String(length=48), nullable=True))
        batch_op.create_index('ix_users_global_user_id', ['global_user_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_global_user_id')
        batch_op.drop_column('global_user_id')
