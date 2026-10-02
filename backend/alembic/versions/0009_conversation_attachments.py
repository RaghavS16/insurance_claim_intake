"""Persist claimant-side attachment metadata on conversation turns."""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _has_baseline():
    bind = op.get_bind()
    return (
        bind.dialect.name == "postgresql"
        and bind.execute(
            sa.text("SELECT to_regclass('public.schema_baseline')")
        ).scalar()
        is not None
    )

def upgrade():
    # 0000 creates the ORM metadata, including attachment, on fresh databases.
    # Historical databases without the baseline must still receive the column.
    if _has_baseline():
        return
    inspector = sa.inspect(op.get_bind())
    if "attachment" not in {c["name"] for c in inspector.get_columns("conversation_turns")}:
        op.add_column(
            "conversation_turns",
            sa.Column("attachment", sa.JSON(), nullable=True),
        )


def downgrade():
    if _has_baseline():
        return
    inspector = sa.inspect(op.get_bind())
    if "attachment" in {c["name"] for c in inspector.get_columns("conversation_turns")}:
        op.drop_column("conversation_turns", "attachment")
