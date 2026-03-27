from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.database import Base


class Station(Base):
    __tablename__ = "station"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    line_id = Column(String(64), default="", index=True)
    edge_device_id = Column(String(128), default="", index=True)
    rtsp_url = Column(String(512), default="")
    description = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workorders = relationship("WorkOrder", back_populates="station")
    alerts = relationship("AlertEvent", back_populates="station")
