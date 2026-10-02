"""Baseline the current SQLAlchemy production schema.

Fresh databases are created from the canonical ORM metadata. Existing
pre-Alembic databases must be explicitly stamped at 0012 after verification;
they must never be rebuilt automatically.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # pgvector is a production dependency of the knowledge store.
    bind.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "vector"'))

    # The ORM metadata is the baseline representation. Subsequent historical
    # revisions are retained for upgrade provenance but become no-ops on a
    # database created by this baseline.
    from src.database.models import Base
    from src.database import hardening_models  # noqa: F401
    Base.metadata.create_all(bind=bind)

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        bind.execute(sa.text(
            "DO $$ BEGIN "
            "ALTER TABLE users ADD CONSTRAINT users_role_check "
            "CHECK (role IN ('CLAIMANT', 'ADJUSTER', 'ADMIN')); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        ))

    if "knowledge_chunks" in tables:
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_hnsw "
            "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
        ))

    op.create_table(
        "schema_baseline",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    bind.execute(sa.text(
        "INSERT INTO schema_baseline (id, revision) VALUES (1, '0000') "
        "ON CONFLICT (id) DO NOTHING"
    ))


def downgrade() -> None:
    op.drop_table("schema_baseline")
    from src.database.models import Base
    Base.metadata.drop_all(bind=op.get_bind())
