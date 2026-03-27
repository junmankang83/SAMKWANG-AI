"""
FastAPI 의존성: 인증·관리자 권한
"""
from typing import Optional, Union

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .database import get_db
from .models.login_account import LoginAccount
from .models.user import User
from .services.auth_service import (
    get_login_by_email,
    get_user_by_username,
    resolve_is_admin,
    verify_token,
)


def _bearer_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def get_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(_bearer_token),
) -> Union[User, LoginAccount]:
    """Authorization: Bearer JWT 필수. `login` 테이블(이메일) 또는 기존 `users` 테이블."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = str(payload["sub"])
    account = get_login_by_email(db, sub)
    if account:
        if account.is_locked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="사용자를 찾을 수 없습니다.",
            )
        return account
    user = get_user_by_username(db, sub)
    if not user or user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )
    return user


def require_admin(
    user: Union[User, LoginAccount] = Depends(get_current_user),
) -> Union[User, LoginAccount]:
    """DB·환경변수 기준 관리자만 허용."""
    if resolve_is_admin(user):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="관리자만 접근할 수 있습니다.",
    )
