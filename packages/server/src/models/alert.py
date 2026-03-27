from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.database import Base


class AlertEvent(Base):
    __tablename__ = "alert_event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workorder_id = Column(Integer, ForeignKey("work_order.id"), nullable=True, index=True)
    station_id = Column(Integer, ForeignKey("station.id"), nullable=True, index=True)
    step_index = Column(Integer, default=0)
    alert_type = Column(String(64), nullable=False, index=True)
    severity = Column(String(32), default="warning")
    message = Column(Text, default="")
    video_url = Column(String(512), default="")
    acknowledged = Column(String(8), default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workorder = relationship("WorkOrder", back_populates="alerts")
    station = relationship("Station", back_populates="alerts")
