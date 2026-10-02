"""Persist claimant-side attachment metadata on conversation turns."""
from alembic import op
import sqlalchemy as sa
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("conversation_turns")}
    if "attachment" not in columns:
        op.add_column("conversation_turns", sa.Column("attachment", sa.JSON(), nullable=True))

def downgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("conversation_turns")}
    if "attachment" in columns:
        op.drop_column("conversation_turns", "attachment")
