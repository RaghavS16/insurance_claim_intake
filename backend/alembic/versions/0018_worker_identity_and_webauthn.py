"""Add explicit adjuster identity, voice worker affinity, and WebAuthn state."""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _baseline() -> bool:
    bind = op.get_bind()
    return (
        bind.dialect.name == "postgresql"
        and bind.execute(sa.text("SELECT to_regclass('public.schema_baseline')")).scalar() is not None
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _baseline():
        return

    def add_column(table: str, column: sa.Column) -> None:
        if inspector.has_table(table) and column.name not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, column)

    add_column("adjusters", sa.Column("user_id", sa.String(36), nullable=True))
    add_column("voice_sessions", sa.Column("worker_id", sa.String(120), nullable=False, server_default="unknown"))
    add_column("voice_sessions", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))

    if inspector.has_table("adjusters"):
        op.create_index("ix_adjusters_user_id", "adjusters", ["user_id"], unique=True, if_not_exists=True)
    if inspector.has_table("voice_sessions"):
        op.create_index("ix_voice_sessions_worker_id", "voice_sessions", ["worker_id"], if_not_exists=True)

    if inspector.has_table("webauthn_credentials"):
        return

    op.create_table(
        "webauthn_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.String(512), nullable=False, unique=True),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("device_type", sa.String(80), nullable=True),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webauthn_credentials_tenant_id", "webauthn_credentials", ["tenant_id"])
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])

    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("challenge", sa.String(512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_webauthn_challenges_tenant_id", "webauthn_challenges", ["tenant_id"])
    op.create_index("ix_webauthn_challenges_user_id", "webauthn_challenges", ["user_id"])
    op.create_index("ix_webauthn_challenges_consumed", "webauthn_challenges", ["consumed", "expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _baseline():
        return
    if inspector.has_table("webauthn_challenges"):
        op.drop_index("ix_webauthn_challenges_consumed", table_name="webauthn_challenges", if_exists=True)
        op.drop_index("ix_webauthn_challenges_user_id", table_name="webauthn_challenges", if_exists=True)
        op.drop_index("ix_webauthn_challenges_tenant_id", table_name="webauthn_challenges", if_exists=True)
        op.drop_table("webauthn_challenges")
    if inspector.has_table("webauthn_credentials"):
        op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials", if_exists=True)
        op.drop_index("ix_webauthn_credentials_tenant_id", table_name="webauthn_credentials", if_exists=True)
        op.drop_table("webauthn_credentials")
    if inspector.has_table("voice_sessions"):
        op.drop_index("ix_voice_sessions_worker_id", table_name="voice_sessions", if_exists=True)
        for col in ("lease_expires_at", "worker_id"):
            if col in {c["name"] for c in inspector.get_columns("voice_sessions")}:
                op.drop_column("voice_sessions", col)
    if inspector.has_table("adjusters") and "user_id" in {c["name"] for c in inspector.get_columns("adjusters")}:
        op.drop_index("ix_adjusters_user_id", table_name="adjusters", if_exists=True)
        op.drop_column("adjusters", "user_id")
