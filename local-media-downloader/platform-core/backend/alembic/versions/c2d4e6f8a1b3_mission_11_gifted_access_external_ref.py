"""mission 11: gifted_access external_ref (persisted source preservation)

Revision ID: c2d4e6f8a1b3
Revises: b1c3d5e7f9a0
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d4e6f8a1b3'
down_revision: Union[str, None] = 'b1c3d5e7f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('gifted_access') as batch_op:
        batch_op.add_column(sa.Column('external_ref', sa.String(length=200), nullable=True))
        batch_op.create_unique_constraint('uq_gifted_access_external_ref', ['external_ref'])


def downgrade() -> None:
    with op.batch_alter_table('gifted_access') as batch_op:
        batch_op.drop_constraint('uq_gifted_access_external_ref', type_='unique')
        batch_op.drop_column('external_ref')
