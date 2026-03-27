"""add cleanup_log table

Revision ID: 20250327_01
Revises:
Create Date: 2025-03-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20250327_01"
down_revision: Union[str, None] = "20250327_00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cleanup_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cleanup_type", sa.String(length=50), nullable=False),
        sa.Column("records_cleaned", sa.Integer(), nullable=True),
        sa.Column("objects_deleted", sa.Integer(), nullable=True),
        sa.Column("bytes_freed", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("cleanup_log")
