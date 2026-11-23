"""conversation mode

Revision ID: c5f1d8a3b7e2
Revises: a9e4b6c2d815
Create Date: 2026-11-22 12:00:00

CODEBASE-FEATURE (Stage 4). Adds ONE column to conversations:
  mode   'docs' (questions about uploaded documents) or 'code' (questions about source code).
         NOT NULL with default 'docs': every existing row becomes 'docs' and the database itself guarantees a
         value, so no code has to treat null as docs. A CHECK constraint refuses any other value.

Safe on a live table: adding a column with a constant default is a metadata-only change on Postgres 11+ (no table
rewrite); the CHECK is validated once against the existing rows, which all hold 'docs'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5f1d8a3b7e2"
down_revision: Union[str, Sequence[str], None] = "a9e4b6c2d815"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("mode", sa.String(length=10), nullable=False, server_default="docs"))
    op.create_check_constraint("ck_conversations_mode", "conversations", "mode IN ('docs', 'code')")


def downgrade() -> None:
    op.drop_constraint("ck_conversations_mode", "conversations", type_="check")
    op.drop_column("conversations", "mode")
