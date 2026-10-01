"""Persist managed realtime voice session lifecycle metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "voice_sessions" not in tables:
        op.create_table(
            "voice_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("call_id", sa.String(200), nullable=False),
            sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("provider", sa.String(60), nullable=False),
            sa.Column("model", sa.String(120), nullable=False),
            sa.Column("status", sa.String(40), nullable=False, server_default="connecting"),
            sa.Column("close_reason", sa.String(200), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.UniqueConstraint("call_id", name="uq_voice_sessions_call_id"),
        )
        op.create_index("ix_voice_sessions_claim", "voice_sessions", ["claim_id"])
        op.create_index("ix_voice_sessions_user", "voice_sessions", ["user_id"])
        op.create_index("ix_voice_sessions_status", "voice_sessions", ["status"])


def downgrade():
    op.drop_index("ix_voice_sessions_status", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_user", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_claim", table_name="voice_sessions")
    op.drop_table("voice_sessions")
