"""Add phone column to adjusters table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "adjusters" in tables:
        adjuster_columns = [col["name"] for col in inspector.get_columns("adjusters")]
        if "phone" not in adjuster_columns:
            op.add_column("adjusters", sa.Column("phone", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "adjusters" in tables:
        adjuster_columns = [col["name"] for col in inspector.get_columns("adjusters")]
        if "phone" in adjuster_columns:
            op.drop_column("adjusters", "phone")
