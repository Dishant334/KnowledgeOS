"""conversation public id

Revision ID: a9e4b6c2d815
Revises: f3c8a1d27b90
Create Date: 2026-11-09 18:00:00

Adds conversations.public_id: a random UUID used in every API route and URL (/chat/<uuid>) instead of the
sequential integer id, which stays internal (foreign keys, messages, document links keep using it).
Existing rows get a UUID during the migration (gen_random_uuid() is evaluated per row); no data is lost.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a9e4b6c2d815"
down_revision: Union[str, Sequence[str], None] = "f3c8a1d27b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
    )
    op.create_index("ix_conversations_public_id", "conversations", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_conversations_public_id", table_name="conversations")
    op.drop_column("conversations", "public_id")
