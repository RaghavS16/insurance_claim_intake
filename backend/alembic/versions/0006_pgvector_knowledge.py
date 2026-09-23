"""Add pgvector-backed knowledge documents/chunks."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision="0006"
down_revision="0005"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("id",sa.String(),primary_key=True),
        sa.Column("source_name",sa.String(),nullable=False),
        sa.Column("source_uri",sa.String(),nullable=False),
        sa.Column("document_type",sa.String(),nullable=False),
        sa.Column("insurance_type",sa.String(),nullable=True),
        sa.Column("content_sha256",sa.String(64),nullable=False),
        sa.Column("uploaded_by",sa.String(),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("metadata_json",sa.JSON(),nullable=False,server_default="{}"),
        sa.Column("created_at",sa.DateTime(),server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_documents_document_type","knowledge_documents",["document_type"])
    op.create_index("ix_knowledge_documents_insurance_type","knowledge_documents",["insurance_type"])
    op.create_table(
        "knowledge_chunks",
        sa.Column("id",sa.String(),primary_key=True),
        sa.Column("document_id",sa.String(),sa.ForeignKey("knowledge_documents.id",ondelete="CASCADE"),nullable=False),
        sa.Column("chunk_index",sa.Integer(),nullable=False),
        sa.Column("text",sa.Text(),nullable=False),
        sa.Column("embedding",Vector(768),nullable=False),
        sa.Column("metadata_json",sa.JSON(),nullable=False,server_default="{}"),
    )
    op.create_index("ix_knowledge_chunks_document_id","knowledge_chunks",["document_id"])
    op.execute("CREATE INDEX knowledge_chunks_embedding_hnsw ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)")

def downgrade():
    op.drop_index("knowledge_chunks_embedding_hnsw",table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    for n in ["ix_knowledge_documents_insurance_type","ix_knowledge_documents_document_type"]:
        op.drop_index(n,table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
