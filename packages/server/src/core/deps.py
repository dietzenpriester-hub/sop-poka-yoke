"""依赖注入"""

from src.core.database import get_db
from src.core.security import get_current_user, require_admin

__all__ = ["get_db", "get_current_user", "require_admin"]
