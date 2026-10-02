"""Add TOTP MFA state and durable challenge/recovery records."""
from alembic import op
import sqlalchemy as sa
revision="0015"
down_revision="0014"
branch_labels=None
depends_on=None

def _baseline():
    b=op.get_bind()
    return b.dialect.name=="postgresql" and b.execute(sa.text("SELECT to_regclass('public.schema_baseline')")).scalar() is not None

def upgrade():
    if _baseline(): return
    op.add_column("users",sa.Column("mfa_enabled",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column("users",sa.Column("mfa_secret_encrypted",sa.String(512),nullable=True))
    op.create_table(
        "mfa_challenges",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("challenge_token_hash",sa.String(128),nullable=False),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("attempts",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("consumed",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("challenge_token_hash",name="uq_mfa_challenge_token_hash"),
    )
    op.create_index("ix_mfa_challenges_user_expires","mfa_challenges",["user_id","expires_at"])
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("code_hash",sa.String(128),nullable=False),
        sa.Column("consumed",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("user_id","code_hash",name="uq_mfa_recovery_user_code"),
    )
    op.create_index("ix_mfa_recovery_user","mfa_recovery_codes",["user_id","consumed"])

def downgrade():
    if _baseline(): return
    op.drop_index("ix_mfa_recovery_user",table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_index("ix_mfa_challenges_user_expires",table_name="mfa_challenges")
    op.drop_table("mfa_challenges")
    op.drop_column("users","mfa_secret_encrypted")
    op.drop_column("users","mfa_enabled")
