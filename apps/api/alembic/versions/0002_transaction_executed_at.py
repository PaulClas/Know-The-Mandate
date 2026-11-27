"""transactions.executed_at: budgets are counted by execution time

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa

from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('executed_at', sa.String(), nullable=True))
    # Backfill: for rows that already reserved or moved money, the last update is the best available execution time.
    op.execute("UPDATE transactions SET executed_at = updated_at WHERE status IN ('RESERVED', 'EXECUTED')")


def downgrade() -> None:
    op.drop_column('transactions', 'executed_at')
