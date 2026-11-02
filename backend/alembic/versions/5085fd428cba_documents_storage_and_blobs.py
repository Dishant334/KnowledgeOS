"""documents storage columns, per-user dedup, document_blobs

Revision ID: 5085fd428cba
Revises: 559a0bb3d9ba
Create Date: 2026-11-02 19:35:46

Brings the schema in line with the Document / DocumentBlob models.

Safe on existing data: new NOT NULL columns are added nullable first and then
tightened. If any existing row would violate NOT NULL, SET NOT NULL fails and
the whole (transactional) migration rolls back instead of leaving a partial
schema. Downgrade drops document_blobs and the new columns (destroys their data).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5085fd428cba"
down_revision: Union[str, Sequence[str], None] = "559a0bb3d9ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("storage_key", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("document_hash", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("error_message", sa.String(length=1000), nullable=True))

    op.alter_column("documents", "storage_key", existing_type=sa.String(length=64), nullable=False)
    op.alter_column("documents", "document_hash", existing_type=sa.String(length=64), nullable=False)

    op.create_index(op.f("ix_documents_document_hash"), "documents", ["document_hash"], unique=False)
    op.create_unique_constraint(
        "uq_documents_user_id_document_hash", "documents", ["user_id", "document_hash"]
    )

    op.create_table(
        "document_blobs",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id"),
    )


def downgrade() -> None:
    op.drop_table("document_blobs")
    op.drop_constraint("uq_documents_user_id_document_hash", "documents", type_="unique")
    op.drop_index(op.f("ix_documents_document_hash"), table_name="documents")
    op.drop_column("documents", "error_message")
    op.drop_column("documents", "document_hash")
    op.drop_column("documents", "storage_key")
