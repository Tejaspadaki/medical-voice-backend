from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.user import User
from app.models.role import Role
from app.models.doctor import Doctor
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.core.config import settings
from app.core.dependencies import blacklist_token

class AuthService:
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def create_tokens_for_user(user: User) -> Tuple[str, str, int]:
        role_name = user.role.name if user.role else "Unknown"
        claims = {
            "email": user.email,
            "role": role_name,
            "full_name": user.full_name or ""
        }
        access_token = create_access_token(subject=user.user_id, extra_claims=claims)
        refresh_token = create_refresh_token(subject=user.user_id, extra_claims={"email": user.email})
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return access_token, refresh_token, expires_in

    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> Tuple[str, int]:
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

        user = db.query(User).filter(User.user_id == user_id, User.is_active == True).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        role_name = user.role.name if user.role else "Unknown"
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
