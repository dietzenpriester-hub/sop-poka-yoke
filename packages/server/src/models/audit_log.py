"""审计日志模型 — 记录用户操作"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from src.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(64), nullable=False, default="", index=True)
    action = Column(String(32), nullable=False, index=True)
    resource = Column(String(64), nullable=False, index=True)
    resource_id = Column(String(64), nullable=True)
    detail = Column(Text, nullable=False, default="")
    ip_address = Column(String(45), nullable=False, default="")
    user_agent = Column(String(256), nullable=False, default="")
    status_code = Column(Integer, nullable=False, default=200)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
