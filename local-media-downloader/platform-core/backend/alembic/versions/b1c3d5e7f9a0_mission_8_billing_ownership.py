"""mission 8: billing ownership transition - out-of-order webhook guard

Revision ID: b1c3d5e7f9a0
Revises: 6e61dba98356
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database.sa_types


# revision identifiers, used by Alembic.
revision: str = 'b1c3d5e7f9a0'
down_revision: Union[str, None] = '6e61dba98356'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.add_column(
            sa.Column('last_event_occurred_at', app.database.sa_types.UTCDateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.drop_column('last_event_occurred_at')
