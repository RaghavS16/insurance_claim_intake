"""Add transactional outbox."""
from alembic import op
import sqlalchemy as sa
revision="0014"
down_revision="0013"
branch_labels=None
depends_on=None

def _baseline():
    b=op.get_bind()
    return b.dialect.name=="postgresql" and b.execute(sa.text("SELECT to_regclass('public.schema_baseline')")).scalar() is not None

def upgrade():
    if _baseline(): return
    op.create_table(
        "outbox_events",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("event_type",sa.String(150),nullable=False),
        sa.Column("aggregate_type",sa.String(100),nullable=False),
        sa.Column("aggregate_id",sa.String(150),nullable=False),
        sa.Column("payload_json",sa.JSON(),nullable=False),
        sa.Column("idempotency_key",sa.String(200),nullable=False),
        sa.Column("status",sa.String(30),nullable=False,server_default="pending"),
        sa.Column("attempts",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("next_attempt_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("locked_at",sa.DateTime(timezone=True)),
        sa.Column("processed_at",sa.DateTime(timezone=True)),
        sa.Column("last_error",sa.Text()),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("idempotency_key",name="uq_outbox_events_idempotency"),
    )
    op.create_index("ix_outbox_events_dispatch","outbox_events",["status","next_attempt_at"])
    op.create_index("ix_outbox_events_status","outbox_events",["status"])
    op.create_index("ix_outbox_events_next_attempt_at","outbox_events",["next_attempt_at"])

def downgrade():
    if _baseline(): return
    op.drop_index("ix_outbox_events_next_attempt_at",table_name="outbox_events")
    op.drop_index("ix_outbox_events_status",table_name="outbox_events")
    op.drop_index("ix_outbox_events_dispatch",table_name="outbox_events")
    op.drop_table("outbox_events")
