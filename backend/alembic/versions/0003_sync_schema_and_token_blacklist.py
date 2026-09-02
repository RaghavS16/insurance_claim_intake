"""Sync schema and add revoked_tokens table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_active and policyholder_phone to policies if not present
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    policy_columns = [col["name"] for col in inspector.get_columns("policies")]

    if "is_active" not in policy_columns:
        op.add_column("policies", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "policyholder_phone" not in policy_columns:
        op.add_column("policies", sa.Column("policyholder_phone", sa.String(), nullable=True))
    if "policyholder_phone_last4" not in policy_columns:
        op.add_column("policies", sa.Column("policyholder_phone_last4", sa.String(4), nullable=True))

    tables = inspector.get_table_names()
    if "revoked_tokens" not in tables:
        op.create_table(
            "revoked_tokens",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("token_jti", sa.String(), unique=True, nullable=False, index=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "revoked_tokens" in tables:
        op.drop_table("revoked_tokens")
    policy_columns = [col["name"] for col in inspector.get_columns("policies")]
    if "is_active" in policy_columns:
        op.drop_column("policies", "is_active")
