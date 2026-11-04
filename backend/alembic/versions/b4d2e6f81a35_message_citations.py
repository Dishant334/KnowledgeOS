"""message citations

Revision ID: b4d2e6f81a35
Revises: 7c1e9a4b2d03
Create Date: 2026-11-05 12:00:00

Adds one NULLABLE column to messages, so existing rows are untouched:
  citations   the sources an assistant answer cited (a JSON list of citation objects;
              NULL for user messages and for answers saved before this column existed)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b4d2e6f81a35"
down_revision: Union[str, Sequence[str], None] = "7c1e9a4b2d03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("citations", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # Destroys the stored citations (the messages themselves are not affected).
    op.drop_column("messages", "citations")
