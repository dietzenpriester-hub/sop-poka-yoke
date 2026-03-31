from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.database import Base


class WorkOrder(Base):
    __tablename__ = "work_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sn = Column(String(100), nullable=False, index=True)
    station_id = Column(Integer, ForeignKey("station.id"), nullable=True, index=True)
    sop_template_id = Column(Integer, ForeignKey("sop_template.id"), nullable=True)
    status = Column(String(32), default="running")
    operator_id = Column(Integer, ForeignKey("user_account.id"), nullable=True)
    extra = Column(JSON, default=dict)
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)

    template = relationship("SOPTemplate", back_populates="workorders")
    station = relationship("Station", back_populates="workorders")
    step_records = relationship("StepRecord", back_populates="workorder", cascade="all, delete-orphan")
    alerts = relationship("AlertEvent", back_populates="workorder")


class StepRecord(Base):
    __tablename__ = "step_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workorder_id = Column(Integer, ForeignKey("work_order.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    step_name = Column(String(200), default="")
    result = Column(String(32), nullable=False)
    confidence = Column(String(32), default="0")
    snapshot_url = Column(String(512), default="")
    video_url = Column(String(512), default="")
    detail = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    workorder = relationship("WorkOrder", back_populates="step_records")
