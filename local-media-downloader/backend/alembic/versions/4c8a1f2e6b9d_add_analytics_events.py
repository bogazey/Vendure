"""add analytics_events

Revision ID: 4c8a1f2e6b9d
Revises: 9f1c6a4e7d2b
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c8a1f2e6b9d'
down_revision: Union[str, None] = '9f1c6a4e7d2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'analytics_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('visitor_id', sa.String(length=64), nullable=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=True),
        sa.Column('locale', sa.String(length=5), nullable=True),
        sa.Column('referrer_domain', sa.String(length=255), nullable=True),
        sa.Column('utm_source', sa.String(length=100), nullable=True),
        sa.Column('utm_medium', sa.String(length=100), nullable=True),
        sa.Column('utm_campaign', sa.String(length=100), nullable=True),
        sa.Column('job_id', sa.String(length=64), nullable=True),
        sa.Column('source_platform', sa.String(length=20), nullable=True),
        sa.Column('media_type', sa.String(length=20), nullable=True),
        sa.Column('format', sa.String(length=30), nullable=True),
        sa.Column('failure_category', sa.String(length=40), nullable=True),
        sa.Column('plan', sa.String(length=20), nullable=True),
        sa.Column('from_plan', sa.String(length=20), nullable=True),
        sa.Column('country_code', sa.String(length=2), nullable=True),
        sa.Column('device_type', sa.String(length=20), nullable=True),
        sa.Column('browser_family', sa.String(length=30), nullable=True),
        sa.Column('os_family', sa.String(length=30), nullable=True),
        sa.Column('client', sa.String(length=20), nullable=False, server_default='web'),
    )
    op.create_index('ix_analytics_events_event_type', 'analytics_events', ['event_type'])
    op.create_index('ix_analytics_events_visitor_id', 'analytics_events', ['visitor_id'])
    op.create_index('ix_analytics_events_user_id', 'analytics_events', ['user_id'])
    op.create_index('ix_analytics_events_timestamp', 'analytics_events', ['timestamp'])
    op.create_index('ix_analytics_events_path', 'analytics_events', ['path'])
    op.create_index('ix_analytics_events_job_id', 'analytics_events', ['job_id'])
    op.create_index('ix_analytics_events_type_ts', 'analytics_events', ['event_type', 'timestamp'])


def downgrade() -> None:
    op.drop_index('ix_analytics_events_type_ts', table_name='analytics_events')
    op.drop_index('ix_analytics_events_job_id', table_name='analytics_events')
    op.drop_index('ix_analytics_events_path', table_name='analytics_events')
    op.drop_index('ix_analytics_events_timestamp', table_name='analytics_events')
    op.drop_index('ix_analytics_events_user_id', table_name='analytics_events')
    op.drop_index('ix_analytics_events_visitor_id', table_name='analytics_events')
    op.drop_index('ix_analytics_events_event_type', table_name='analytics_events')
    op.drop_table('analytics_events')
