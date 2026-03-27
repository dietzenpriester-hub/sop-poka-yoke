from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from src.core.database import Base


class UserAccount(Base):
    __tablename__ = "user_account"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    display_name = Column(String(128), default="")
    role = Column(String(32), default="operator")
    badge_id = Column(String(64), default="", index=True)
    password_hash = Column(String(256), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
