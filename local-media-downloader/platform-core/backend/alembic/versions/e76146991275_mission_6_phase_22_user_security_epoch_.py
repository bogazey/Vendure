"""mission 6 phase 22: user security_epoch for sign-out-all

Revision ID: e76146991275
Revises: 4a35a2c457fb
Create Date: 2026-09-14 02:57:04.191268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e76146991275'
down_revision: Union[str, None] = '4a35a2c457fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A server_default is required here (not just the ORM-level Python
    # default=1) because this column is NOT NULL and this migration must
    # apply cleanly against a POPULATED V1 users table (mission-brief
    # Phase 46) - every existing row needs a real value the instant the
    # column exists, not just new rows inserted after this migration.
    # Dropped again immediately after backfill so the column's long-term
    # definition matches the ORM model exactly (no lingering DB-level
    # default the model doesn't declare).
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('security_epoch', sa.Integer(), nullable=False, server_default='1'))
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('security_epoch', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('security_epoch')
