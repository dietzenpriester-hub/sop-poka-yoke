"""add learning_task table

Revision ID: 20250327_02
Revises: 20250327_01
Create Date: 2025-03-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20250327_02"
down_revision: Union[str, None] = "20250327_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_task",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("product_model", sa.String(length=100), nullable=False),
        sa.Column("process_name", sa.String(length=100), nullable=False),
        sa.Column("video_path", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("analysis_detail", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_task_task_id"), "learning_task", ["task_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_learning_task_task_id"), table_name="learning_task")
    op.drop_table("learning_task")
