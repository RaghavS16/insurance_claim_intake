"""Policy ownership and admin role migration

Revision ID: 0001
Revises: None
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users: allow ADMIN role ---
    try:
        op.drop_constraint("users_role_check", "users", type_="check")
    except Exception:
        pass
    op.create_check_constraint(
        "users_role_check", "users",
        "role IN ('CLAIMANT', 'ADJUSTER', 'ADMIN')"
    )

    # --- policies: fix customer_id, add PII + link tracking columns ---
    op.alter_column("policies", "customer_id", nullable=True, server_default=None)
    op.create_foreign_key(
        "fk_policies_customer", "policies", "users",
        ["customer_id"], ["id"]
    )
    op.add_column("policies", sa.Column("policyholder_name", sa.String(), nullable=True))
    op.add_column("policies", sa.Column("policyholder_dob", sa.Date(), nullable=True))
    op.add_column("policies", sa.Column("policyholder_phone_last4", sa.String(4), nullable=True))
    op.add_column("policies", sa.Column("linked_at", sa.DateTime(), nullable=True))
    op.add_column("policies", sa.Column("link_attempts", sa.Integer(), nullable=False, server_default="0"))

    # --- new audit table ---
    op.create_table(
        "policy_link_audit",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("policy_number", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("policy_link_audit")
    op.drop_column("policies", "link_attempts")
    op.drop_column("policies", "linked_at")
    op.drop_column("policies", "policyholder_phone_last4")
    op.drop_column("policies", "policyholder_dob")
    op.drop_column("policies", "policyholder_name")
    op.drop_constraint("fk_policies_customer", "policies", type_="foreignkey")
    op.alter_column("policies", "customer_id", nullable=False)
    op.drop_constraint("users_role_check", "users", type_="check")
    op.create_check_constraint("users_role_check", "users", "role IN ('CLAIMANT', 'ADJUSTER')")
