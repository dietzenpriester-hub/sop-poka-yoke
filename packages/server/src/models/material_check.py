from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.database import Base


class MaterialCheck(Base):
    __tablename__ = "material_check"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workorder_id = Column(Integer, ForeignKey("work_order.id"), nullable=False, index=True)
    bom_item = Column(String(100), nullable=False)
    detected_material = Column(String(200), default="")
    result = Column(String(32), nullable=False)
    confidence = Column(Float, default=0.0)
    snapshot_url = Column(String(512), default="")
    detail = Column(Text, default="")
    checked_at = Column(DateTime(timezone=True), server_default=func.now())

    workorder = relationship("WorkOrder", backref="material_checks")
