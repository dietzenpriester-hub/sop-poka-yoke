from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.database import Base


class OverrideLog(Base):
    __tablename__ = "override_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workorder_id = Column(Integer, ForeignKey("work_order.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    operator_badge = Column(String(64), nullable=False)
    reason = Column(Text, default="")
    video_url = Column(String(512), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workorder = relationship("WorkOrder", backref="override_logs")
