"""align_indexes_and_constraints

Revision ID: 0022
Revises: 0021
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_conversation_turns_event_id", table_name="conversation_turns", if_exists=True)
    op.drop_index("ix_knowledge_documents_content_sha256", table_name="knowledge_documents", if_exists=True)


def downgrade() -> None:
    op.create_index("ix_knowledge_documents_content_sha256", "knowledge_documents", ["content_sha256"], unique=False)
    op.create_index("ix_conversation_turns_event_id", "conversation_turns", ["event_id"], unique=True)
