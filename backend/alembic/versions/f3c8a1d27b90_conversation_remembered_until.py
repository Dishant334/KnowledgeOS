"""conversation remembered until

Revision ID: f3c8a1d27b90
Revises: d7a3c91e4f20
Create Date: 2026-11-09 12:00:00

Adds ONE nullable column to conversations (existing rows untouched):
  remembered_until_message_id   messages with id <= this value were already given to the long-term memory step
                                (an LLM call per conversation), so the same messages never cost a second call.
                                A plain number marking a position (like summarized_until_message_id), not a key.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3c8a1d27b90"
down_revision: Union[str, Sequence[str], None] = "d7a3c91e4f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("remembered_until_message_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "remembered_until_message_id")
