from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status

from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.core.config import settings
from app.core.dependencies import blacklist_token, MongoUser

class AuthService:
    @staticmethod
    def authenticate_user(db: Any, email: str, password: str) -> Optional[MongoUser]:
        user_doc = db.users.find_one({"email": email})
        if not user_doc:
            return None
        if not verify_password(password, user_doc.get("hashed_password", "")):
            return None
        return MongoUser(user_doc)

    @staticmethod
    def create_tokens_for_user(user: Any) -> Tuple[str, str, int]:
        role_name = user.role.name if hasattr(user, "role") and user.role else (user.get("role_name") if hasattr(user, "get") else "Doctor")
        claims = {
            "email": getattr(user, "email", user.get("email") if hasattr(user, "get") else ""),
            "role": role_name,
            "full_name": getattr(user, "full_name", user.get("full_name") if hasattr(user, "get") else "")
        }
        user_id = getattr(user, "user_id", user.get("user_id") if hasattr(user, "get") else None)
        access_token = create_access_token(subject=user_id, extra_claims=claims)
        refresh_token = create_refresh_token(subject=user_id, extra_claims={"email": claims["email"]})
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return access_token, refresh_token, expires_in

    @staticmethod
    def refresh_access_token(db: Any, refresh_token: str) -> Tuple[str, int]:
        payload = decode_token(refresh_token)
        if payload is None or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )

        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims"
            )

        try:
            user_id = int(user_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user identification in token"
            )

        user_doc = db.users.find_one({"user_id": user_id, "is_active": True})
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        user = MongoUser(user_doc)
        role_name = user.role_name
        claims = {
            "email": user.email,
            "role": role_name,
            "full_name": user.full_name or ""
        }
        new_access_token = create_access_token(subject=user.user_id, extra_claims=claims)
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return new_access_token, expires_in

    @staticmethod
    def logout(token: Optional[str]) -> None:
        if token:
            # Blacklist token for duration of access token expiry
            blacklist_token(token, expire_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
