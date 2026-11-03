"""conversation summary

Revision ID: 7c1e9a4b2d03
Revises: 5085fd428cba
Create Date: 2026-11-03 19:00:00

Adds two NULLABLE columns to conversations, so existing rows are untouched:
  summary                       rolling summary of the older messages
  summarized_until_message_id   last message id already folded into the summary
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1e9a4b2d03"
down_revision: Union[str, Sequence[str], None] = "5085fd428cba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("conversations", sa.Column("summarized_until_message_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Destroys the stored summaries (the messages themselves are not affected).
    op.drop_column("conversations", "summarized_until_message_id")
    op.drop_column("conversations", "summary")
