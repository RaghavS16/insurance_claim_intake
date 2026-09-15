"""Add normalized production claim workflow tables."""
from alembic import op
import sqlalchemy as sa
revision="0007"; down_revision="0006"; branch_labels=None; depends_on=None

def upgrade():
    op.create_table("claim_assignments",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("claim_id",sa.String(),sa.ForeignKey("claims.id",ondelete="CASCADE"),nullable=False),
        sa.Column("adjuster_id",sa.String(),sa.ForeignKey("adjusters.id",ondelete="RESTRICT"),nullable=False),sa.Column("assigned_by",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.Column("reason",sa.Text()),sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("assigned_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("unassigned_at",sa.DateTime(timezone=True)))
    op.create_index("ix_claim_assignments_claim_active","claim_assignments",["claim_id","is_active"])
    op.create_index("ix_claim_assignments_adjuster_active","claim_assignments",["adjuster_id","is_active"])
    op.create_table("claim_requirements",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("claim_id",sa.String(),sa.ForeignKey("claims.id",ondelete="CASCADE"),nullable=False),
        sa.Column("requirement_key",sa.String(150),nullable=False),sa.Column("label",sa.String(500),nullable=False),sa.Column("question_hint",sa.Text()),
        sa.Column("status",sa.String(40),nullable=False,server_default="unknown"),sa.Column("required",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("evidence_type",sa.String(100)),sa.Column("condition_json",sa.JSON(),nullable=False,server_default="{}"),sa.Column("provenance_json",sa.JSON(),nullable=False,server_default="{}"),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint("claim_id","requirement_key",name="uq_claim_requirement_key"))
    op.create_index("ix_claim_requirements_status","claim_requirements",["status"])
    op.create_table("claim_evidence",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("claim_id",sa.String(),sa.ForeignKey("claims.id",ondelete="CASCADE"),nullable=False),
        sa.Column("uploaded_by",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("requirement_id",sa.String(36),sa.ForeignKey("claim_requirements.id",ondelete="SET NULL")),
        sa.Column("object_key",sa.String(1000),nullable=False,unique=True),sa.Column("original_filename",sa.String(500),nullable=False),sa.Column("content_type",sa.String(200),nullable=False),
        sa.Column("size_bytes",sa.Integer(),nullable=False),sa.Column("sha256",sa.String(64)),sa.Column("status",sa.String(40),nullable=False,server_default="uploaded"),sa.Column("document_type",sa.String(100)),
        sa.Column("analysis_json",sa.JSON(),nullable=False,server_default="{}"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    for n,c in [("ix_claim_evidence_claim","claim_id"),("ix_claim_evidence_status","status"),("ix_claim_evidence_sha256","sha256")]: op.create_index(n,"claim_evidence",[c])
    op.create_table("claim_decisions",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("claim_id",sa.String(),sa.ForeignKey("claims.id",ondelete="CASCADE"),nullable=False),
        sa.Column("adjuster_id",sa.String(),sa.ForeignKey("adjusters.id",ondelete="RESTRICT"),nullable=False),sa.Column("decision",sa.String(40),nullable=False),
        sa.Column("rationale",sa.Text(),nullable=False),sa.Column("approved_amount",sa.Numeric()),sa.Column("ai_recommendation_json",sa.JSON(),nullable=False,server_default="{}"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_claim_decisions_claim","claim_decisions",["claim_id"])
    op.create_table("claim_notes",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("claim_id",sa.String(),sa.ForeignKey("claims.id",ondelete="CASCADE"),nullable=False),
        sa.Column("author_user_id",sa.String(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("note",sa.Text(),nullable=False),sa.Column("visibility",sa.String(30),nullable=False,server_default="internal"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_claim_notes_claim","claim_notes",["claim_id"])
    op.create_table("claim_audit_events",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("claim_id",sa.String(),sa.ForeignKey("claims.id",ondelete="CASCADE"),nullable=False),
        sa.Column("actor_user_id",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("event_type",sa.String(100),nullable=False),
        sa.Column("old_value_json",sa.JSON(),nullable=False,server_default="{}"),sa.Column("new_value_json",sa.JSON(),nullable=False,server_default="{}"),sa.Column("reason",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_claim_audit_events_claim","claim_audit_events",["claim_id"]); op.create_index("ix_claim_audit_events_type","claim_audit_events",["event_type"])
    op.create_table("copilot_analyses",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("claim_id",sa.String(),sa.ForeignKey("claims.id",ondelete="CASCADE"),nullable=False),
        sa.Column("claim_version",sa.Integer(),nullable=False,server_default="1"),sa.Column("knowledge_version",sa.String(200),nullable=False,server_default="unknown"),
        sa.Column("model",sa.String(200),nullable=False),sa.Column("prompt_version",sa.String(100),nullable=False,server_default="v1"),
        sa.Column("result_json",sa.JSON(),nullable=False,server_default="{}"),sa.Column("citations_json",sa.JSON(),nullable=False,server_default="[]"),sa.Column("stale",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_copilot_analyses_claim","copilot_analyses",["claim_id"]); op.create_index("ix_copilot_analyses_stale","copilot_analyses",["stale"])

def downgrade():
    for n,t in [("ix_copilot_analyses_stale","copilot_analyses"),("ix_copilot_analyses_claim","copilot_analyses"),("ix_claim_audit_events_type","claim_audit_events"),("ix_claim_audit_events_claim","claim_audit_events"),("ix_claim_notes_claim","claim_notes"),("ix_claim_decisions_claim","claim_decisions"),("ix_claim_evidence_sha256","claim_evidence"),("ix_claim_evidence_status","claim_evidence"),("ix_claim_evidence_claim","claim_evidence"),("ix_claim_requirements_status","claim_requirements"),("ix_claim_assignments_adjuster_active","claim_assignments"),("ix_claim_assignments_claim_active","claim_assignments")]:
        op.drop_index(n,table_name=t)
    for t in ["copilot_analyses","claim_audit_events","claim_notes","claim_decisions","claim_evidence","claim_requirements","claim_assignments"]: op.drop_table(t)
