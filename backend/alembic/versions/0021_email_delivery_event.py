from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("adjuster_invitations"):
        columns = {c["name"] for c in inspector.get_columns("adjuster_invitations")}
        if "email_event_id" not in columns:
            op.add_column("adjuster_invitations", sa.Column("email_event_id", sa.String(length=36), nullable=True))
            op.create_index("ix_adjuster_invitations_email_event_id", "adjuster_invitations", ["email_event_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("adjuster_invitations"):
        columns = {c["name"] for c in inspector.get_columns("adjuster_invitations")}
        if "email_event_id" in columns:
            op.drop_index("ix_adjuster_invitations_email_event_id", table_name="adjuster_invitations")
            op.drop_column("adjuster_invitations", "email_event_id")
