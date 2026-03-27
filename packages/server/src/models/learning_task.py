"""SOP 学习任务持久化模型"""

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.sql import func

from src.core.database import Base


class LearningTask(Base):
    __tablename__ = "learning_task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)  # UUID
    product_model = Column(String(100), nullable=False)
    process_name = Column(String(100), nullable=False)
    video_path = Column(String(512), default="")  # MinIO path
    status = Column(String(20), default="queued")  # queued, analyzing, phase_1, phase_2, phase_3, completed, failed, confirmed
    progress = Column(Float, default=0.0)  # 0.0 - 1.0
    steps = Column(JSON, default=list)  # analyzed steps
    analysis_detail = Column(JSON, default=dict)  # detailed analysis info
    error_message = Column(Text, default="")
    template_id = Column(Integer, nullable=True)  # generated template ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
