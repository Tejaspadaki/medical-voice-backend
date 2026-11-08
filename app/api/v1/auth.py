from typing import Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.mongo import get_mongo_db
from app.core.dependencies import get_current_user, MongoUser
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    MessageResponse
)
from app.schemas.user import UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User Login (supports JSON and form-data)",
    description="Authenticate with email/username and password. Returns access and refresh JWT tokens."
)
async def login(
    request: Request,
    db = Depends(get_mongo_db)
):
    # Check if request is JSON or form-data
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        email = body.get("email") or body.get("username")
        password = body.get("password")
    else:
        form = await request.form()
        email = form.get("username") or form.get("email")
        password = form.get("password")

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email/username and password are required"
        )

    user = AuthService.authenticate_user(db, email=email, password=password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact your clinical administrator."
        )

    access_token, refresh_token, expires_in = AuthService.create_tokens_for_user(user)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserOut.model_validate(user)
    )

@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="Refresh Access Token",
    description="Exchange a valid refresh token for a new access token."
)
def refresh_token(
    payload: RefreshTokenRequest,
    db = Depends(get_mongo_db)
):
    access_token, expires_in = AuthService.refresh_access_token(db, payload.refresh_token)
    return RefreshTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in
    )

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="User Logout",
    description="Invalidate current session and blacklist active token."
)
def logout(
    authorization: Optional[str] = Header(None)
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    
    AuthService.logout(token)
    return MessageResponse(message="Successfully logged out and session revoked")

@router.get(
    "/me",
    response_model=UserOut,
    summary="Current User Profile",
    description="Get authenticated user profile details, role, and medical registration."
)
def get_me(
    current_user: MongoUser = Depends(get_current_user)
):
    return current_user
