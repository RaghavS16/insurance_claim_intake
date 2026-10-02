"""Introduce tenant boundaries and backfill legacy records into a default tenant."""
from alembic import op
import sqlalchemy as sa
import uuid
revision="0016"
down_revision="0015"
branch_labels=None
depends_on=None

TABLES=("users","policies","claims","adjusters","voice_sessions")

def _baseline():
    b=op.get_bind()
    return b.dialect.name=="postgresql" and b.execute(sa.text("SELECT to_regclass('public.schema_baseline')")).scalar() is not None

def upgrade():
    if _baseline(): return
    op.create_table(
        "tenants",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("name",sa.String(200),nullable=False),
        sa.Column("status",sa.String(30),nullable=False,server_default="active"),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("tenant_id",sa.String(36),nullable=False),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("role",sa.String(40),nullable=False),
        sa.Column("status",sa.String(30),nullable=False,server_default="active"),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("tenant_id","user_id",name="uq_tenant_membership"),
    )
    op.create_index("ix_tenant_membership_user","tenant_memberships",["user_id"])
    op.create_index("ix_tenant_membership_tenant","tenant_memberships",["tenant_id"])
    for table in TABLES:
        op.add_column(table,sa.Column("tenant_id",sa.String(36),nullable=True))
        op.create_index(f"ix_{table}_tenant_id",table,["tenant_id"])
    tenant_id=str(uuid.uuid4())
    now=sa.func.now()
    op.execute(sa.text("INSERT INTO tenants(id,name,status,created_at) VALUES (:id,'Legacy Tenant','active',now())").bindparams(id=tenant_id))
    for table in TABLES:
        op.execute(sa.text(f"UPDATE {table} SET tenant_id=:tid WHERE tenant_id IS NULL").bindparams(tid=tenant_id))
    op.execute(sa.text("INSERT INTO tenant_memberships(id,tenant_id,user_id,role,status,created_at) SELECT :prefix || substr(id,1,27), tenant_id, id, role, 'active', now() FROM users").bindparams(prefix=tenant_id[:9]))
    # Enforce the boundary for all future core records.
    for table in TABLES:
        op.alter_column(table,"tenant_id",nullable=False)

def downgrade():
    if _baseline(): return
    for table in reversed(TABLES):
        op.alter_column(table,"tenant_id",nullable=True)
        op.drop_index(f"ix_{table}_tenant_id",table_name=table)
        op.drop_column(table,"tenant_id")
    op.drop_index("ix_tenant_membership_tenant",table_name="tenant_memberships")
    op.drop_index("ix_tenant_membership_user",table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
