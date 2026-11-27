"""agent transparency: activity reports, log commitments, agents.transparency

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa

from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agents', sa.Column('transparency', sa.JSON(), nullable=False, server_default='{}'))
    op.create_table('activity_reports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('window_start', sa.String(), nullable=False),
        sa.Column('window_end', sa.String(), nullable=False),
        sa.Column('head', sa.String(), nullable=False),
        sa.Column('entry_count', sa.Integer(), nullable=False),
        sa.Column('discrepancies', sa.JSON(), nullable=False),
        sa.Column('jws', sa.Text(), nullable=False),
        sa.Column('received_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_activity_reports_agent_id', 'activity_reports', ['agent_id'])
    op.create_table('agent_commitments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('commitment', sa.String(), nullable=False),
        sa.Column('ref', sa.String(), nullable=True),
        sa.Column('jws', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('due_at', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('revealed', sa.JSON(), nullable=True),
        sa.Column('revealed_at', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_agent_commitments_agent_id', 'agent_commitments', ['agent_id'])


def downgrade() -> None:
    op.drop_table('agent_commitments')
    op.drop_table('activity_reports')
    op.drop_column('agents', 'transparency')
