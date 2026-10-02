"""Enforce database-level identity and session ownership constraints."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _constraints() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        str(item["name"])
        for table in inspector.get_table_names()
        for item in inspector.get_foreign_keys(table)
        if item.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = _constraints()

    if inspector.has_table("adjusters") and inspector.has_table("users"):
        if "fk_adjusters_user_id_users" not in constraints:
            op.create_foreign_key(
                "fk_adjusters_user_id_users",
                "adjusters",
                "users",
                ["user_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if inspector.has_table("voice_sessions"):
        columns = {c["name"] for c in inspector.get_columns("voice_sessions")}
        if "worker_id" in columns and "lease_expires_at" in columns:
            if "ix_voice_sessions_worker_lease" not in {
                str(i.get("name"))
                for i in inspector.get_indexes("voice_sessions")
            }:
                op.create_index(
                    "ix_voice_sessions_worker_lease",
                    "voice_sessions",
                    ["worker_id", "lease_expires_at"],
                )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("voice_sessions"):
        op.drop_index("ix_voice_sessions_worker_lease", table_name="voice_sessions", if_exists=True)
    if inspector.has_table("adjusters"):
        try:
            op.drop_constraint("fk_adjusters_user_id_users", "adjusters", type_="foreignkey")
        except Exception:
            pass
