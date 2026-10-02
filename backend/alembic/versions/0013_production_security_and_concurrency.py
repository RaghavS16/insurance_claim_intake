"""Production security, concurrency and session hardening.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def add_column(table: str, column: sa.Column) -> None:
        if table in inspector.get_table_names() and column.name not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, column)

    add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))
    add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    add_column("users", sa.Column("mfa_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    add_column("claims", sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"))
    add_column("conversation_turns", sa.Column("event_id", sa.String(length=64), nullable=True))

    # A deterministic event id makes retries safe without relying on turn arithmetic.
    if "conversation_turns" in inspector.get_table_names():
        op.create_index(
            "uq_conversation_turn_event_id",
            "conversation_turns",
            ["event_id"],
            unique=True,
            if_not_exists=True,
        )
        op.create_index(
            "idx_conversation_turns_claim_created",
            "conversation_turns",
            ["claim_id", "created_at", "id"],
            if_not_exists=True,
        )

    if "users" in inspector.get_table_names():
        op.create_index(
            "idx_users_status_role",
            "users",
            ["status", "role"],
            if_not_exists=True,
        )

    if "claims" in inspector.get_table_names():
        op.create_index(
            "idx_claims_claimant_updated",
            "claims",
            ["claimant_id", "updated_at"],
            if_not_exists=True,
        )

    # Normalize the pgvector contract to the application embedding dimension.
    # The application uses 768-dimensional embeddings everywhere.
    if "knowledge_chunks" in inspector.get_table_names():
        row = bind.execute(sa.text("""
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'knowledge_chunks'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
        """)).scalar()
        if row and str(row) != "vector(768)":
            raise RuntimeError(
                f"knowledge_chunks.embedding is {row}; expected vector(768). "
                "Rebuild/re-embed the knowledge index before deploying."
            )

def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "conversation_turns" in inspector.get_table_names():
        op.drop_index("idx_conversation_turns_claim_created", table_name="conversation_turns", if_exists=True)
        op.drop_index("uq_conversation_turn_event_id", table_name="conversation_turns", if_exists=True)
        if "event_id" in {c["name"] for c in inspector.get_columns("conversation_turns")}:
            op.drop_column("conversation_turns", "event_id")
    if "claims" in inspector.get_table_names() and "state_version" in {c["name"] for c in inspector.get_columns("claims")}:
        op.drop_column("claims", "state_version")
    if "users" in inspector.get_table_names():
        for name in ("mfa_required", "last_login_at", "session_version", "email_verified_at"):
            if name in {c["name"] for c in inspector.get_columns("users")}:
                op.drop_column("users", name)
