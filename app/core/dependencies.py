from typing import Generator, Optional, List, Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import redis

from app.core.config import settings
from app.core.security import decode_token
from app.core.logging import logger
from app.db.mongo import get_mongo_db, clean_doc

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

class MongoUser:
    def __init__(self, data: dict):
        self._data = clean_doc(data) or {}
        self.user_id = self._data.get("user_id", 1)
        self.email = self._data.get("email", "")
        self.full_name = self._data.get("full_name", "")
        self.role_id = self._data.get("role_id", 2)
        self.role_name = self._data.get("role_name", "Doctor")
        self.is_active = self._data.get("is_active", True)
        self.created_at = self._data.get("created_at") or datetime.now(timezone.utc)
        
        doc_prof = self._data.get("doctor_profile")
        if doc_prof and isinstance(doc_prof, dict):
            class DoctorStub:
                def __init__(self, d):
                    self.doctor_id = d.get("doctor_id", 1)
                    self.specialization = d.get("specialization", "General Medicine")
                    self.registration_no = d.get("registration_no", "KMC-84920")
                    self.department = d.get("department", "OPD")
                    self.contact_phone = d.get("contact_phone", "+919845012345")
            self.doctor_profile = DoctorStub(doc_prof)
        else:
            self.doctor_profile = None

    @property
    def role(self):
        class RoleStub:
            def __init__(self, role_id, name):
                self.role_id = role_id
                self.name = name
                self.description = f"{name} role"
                self.permissions = []
        return RoleStub(self.role_id, self.role_name)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, item):
        return self._data[item]

    def __contains__(self, item):
        return item in self._data

# In-memory blacklist fallback if redis is unavailable
_memory_blacklist = set()

# Initialize Redis client safely
_redis_client: Optional[redis.Redis] = None
try:
    _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2)
    _redis_client.ping()
except Exception as e:
    logger.warning(f"Redis not available at {settings.REDIS_URL}, using in-memory blacklist fallback: {e}")
    _redis_client = None

def get_redis() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            pass
    return None

def is_token_blacklisted(token: str) -> bool:
    r = get_redis()
    if r:
        try:
            return bool(r.get(f"blacklist:{token}"))
        except Exception:
            pass
    return token in _memory_blacklist

def blacklist_token(token: str, expire_seconds: int = 86400) -> None:
    r = get_redis()
    if r:
        try:
            r.setex(f"blacklist:{token}", expire_seconds, "1")
            return
        except Exception:
            pass
    _memory_blacklist.add(token)

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db = Depends(get_mongo_db)
) -> MongoUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    if is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked/logged out",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise credentials_exception

    user_doc = db.users.find_one({"user_id": user_id})
    if user_doc is None:
        raise credentials_exception
    user = MongoUser(user_doc)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )
    return user

def require_roles(allowed_roles: List[str]) -> Callable:
    def role_checker(current_user: MongoUser = Depends(get_current_user)) -> MongoUser:
        if not current_user.role or current_user.role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires one of roles [{', '.join(allowed_roles)}]"
            )
        return current_user
    return role_checker
