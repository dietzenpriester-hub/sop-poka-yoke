"""数据清理执行日志"""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from src.core.database import Base


class CleanupLog(Base):
    __tablename__ = "cleanup_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cleanup_type = Column(String(50), nullable=False)  # "step_record", "alert", "material_check", "completion_check", "override_log", "full"
    records_cleaned = Column(Integer, default=0)
    objects_deleted = Column(Integer, default=0)
    bytes_freed = Column(Float, default=0.0)  # MB
    status = Column(String(20), default="running")  # running, completed, failed
    error_message = Column(Text, default="")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
