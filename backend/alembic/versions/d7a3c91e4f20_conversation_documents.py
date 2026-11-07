"""conversation documents

Revision ID: d7a3c91e4f20
Revises: b4d2e6f81a35
Create Date: 2026-11-08 12:00:00

Adds ONE new table (existing tables and rows are untouched): which documents belong to which conversation.
A question asked in a conversation searches only that conversation's documents.

  conversation_id  -> conversations.id, ON DELETE CASCADE (deleting a chat removes its links, not the documents)
  document_id      -> documents.id,     ON DELETE CASCADE (deleting a document removes it from every chat)
  uploaded_here    True when the upload made in this chat CREATED the document (False when the file was already
                   in the library and was only attached). Only documents created in a chat are deleted together
                   with that chat when it is abandoned without a single message.
  created_at       when it was attached
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7a3c91e4f20"
down_revision: Union[str, Sequence[str], None] = "b4d2e6f81a35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_documents",
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("uploaded_here", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversation_documents_document_id", "conversation_documents", ["document_id"])


def downgrade() -> None:
    # Removes only the links (documents and conversations stay).
    op.drop_index("ix_conversation_documents_document_id", table_name="conversation_documents")
    op.drop_table("conversation_documents")
