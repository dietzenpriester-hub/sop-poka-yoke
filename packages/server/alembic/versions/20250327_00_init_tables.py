"""create initial tables

Revision ID: 20250327_00
Revises:
Create Date: 2025-03-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20250327_00"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "station",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("line_id", sa.String(64), nullable=True, server_default=""),
        sa.Column("edge_device_id", sa.String(128), nullable=True, server_default=""),
        sa.Column("rtsp_url", sa.String(512), nullable=True, server_default=""),
        sa.Column("description", sa.Text(), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_station_line_id", "station", ["line_id"])
    op.create_index("ix_station_edge_device_id", "station", ["edge_device_id"])

    op.create_table(
        "sop_template",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(20), nullable=True, server_default="1.0"),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("product_model", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_account",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=True, server_default=""),
        sa.Column("role", sa.String(32), nullable=True, server_default="operator"),
        sa.Column("badge_id", sa.String(64), nullable=True, server_default=""),
        sa.Column("password_hash", sa.String(256), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_user_account_badge_id", "user_account", ["badge_id"])

    op.create_table(
        "work_order",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sn", sa.String(100), nullable=False),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("station.id"), nullable=True),
        sa.Column("sop_template_id", sa.Integer(), sa.ForeignKey("sop_template.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=True, server_default="running"),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_order_sn", "work_order", ["sn"])
    op.create_index("ix_work_order_station_id", "work_order", ["station_id"])

    op.create_table(
        "step_record",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workorder_id", sa.Integer(), sa.ForeignKey("work_order.id"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(200), nullable=True, server_default=""),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("confidence", sa.String(32), nullable=True, server_default="0"),
        sa.Column("snapshot_url", sa.String(512), nullable=True, server_default=""),
        sa.Column("video_url", sa.String(512), nullable=True, server_default=""),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_step_record_workorder_id", "step_record", ["workorder_id"])

    op.create_table(
        "alert_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workorder_id", sa.Integer(), sa.ForeignKey("work_order.id"), nullable=True),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("station.id"), nullable=True),
        sa.Column("station_code", sa.String(64), nullable=True, server_default=""),
        sa.Column("step_index", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=True, server_default="WARN"),
        sa.Column("message", sa.Text(), nullable=True, server_default=""),
        sa.Column("video_url", sa.String(512), nullable=True, server_default=""),
        sa.Column("acknowledged", sa.String(8), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_event_workorder_id", "alert_event", ["workorder_id"])
    op.create_index("ix_alert_event_station_id", "alert_event", ["station_id"])
    op.create_index("ix_alert_event_station_code", "alert_event", ["station_code"])
    op.create_index("ix_alert_event_alert_type", "alert_event", ["alert_type"])

    op.create_table(
        "material_check",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workorder_id", sa.Integer(), sa.ForeignKey("work_order.id"), nullable=False),
        sa.Column("bom_item", sa.String(100), nullable=False),
        sa.Column("detected_material", sa.String(200), nullable=True, server_default=""),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("snapshot_url", sa.String(512), nullable=True, server_default=""),
        sa.Column("detail", sa.Text(), nullable=True, server_default=""),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_material_check_workorder_id", "material_check", ["workorder_id"])

    op.create_table(
        "completion_check",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workorder_id", sa.Integer(), sa.ForeignKey("work_order.id"), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("check_items", sa.JSON(), nullable=True),
        sa.Column("completion_photo_url", sa.String(512), nullable=True, server_default=""),
        sa.Column("reference_photo_url", sa.String(512), nullable=True, server_default=""),
        sa.Column("similarity_score", sa.Float(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("defects", sa.Text(), nullable=True, server_default=""),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_completion_check_workorder_id", "completion_check", ["workorder_id"])

    op.create_table(
        "override_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workorder_id", sa.Integer(), sa.ForeignKey("work_order.id"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("operator_badge", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True, server_default=""),
        sa.Column("video_url", sa.String(512), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_override_log_workorder_id", "override_log", ["workorder_id"])


def downgrade() -> None:
    op.drop_table("override_log")
    op.drop_table("completion_check")
    op.drop_table("material_check")
    op.drop_table("alert_event")
    op.drop_table("step_record")
    op.drop_table("work_order")
    op.drop_table("user_account")
    op.drop_table("sop_template")
    op.drop_table("station")
