from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.database import Base


class CompletionCheck(Base):
    __tablename__ = "completion_check"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workorder_id = Column(Integer, ForeignKey("work_order.id"), nullable=False, index=True)
    result = Column(String(32), nullable=False)
    check_items = Column(JSON, default=list)
    completion_photo_url = Column(String(512), default="")
    reference_photo_url = Column(String(512), default="")
    similarity_score = Column(Float, default=0.0)
    defects = Column(Text, default="")
    checked_at = Column(DateTime(timezone=True), server_default=func.now())

    workorder = relationship("WorkOrder", backref="completion_checks")
