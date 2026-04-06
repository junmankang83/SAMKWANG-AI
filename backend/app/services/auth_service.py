"""
JWT·비밀번호 해시·관리자 판별.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.login_account import LoginAccount
from ..models.user import User


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    if not password_hash or not isinstance(password_hash, str):
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(username: str, extra: Optional[dict[str, Any]] = None) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {"sub": username, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> Optional[dict[str, Any]]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_login_by_email(db: Session, email: str) -> Optional[LoginAccount]:
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    return (
        db.query(LoginAccount)
        .filter(func.lower(LoginAccount.email) == normalized)
        .first()
    )


def resolve_is_admin(user: User | LoginAccount) -> bool:
    if user.is_admin:
        return True
    # DB 시드와 동일 목록(도메인 오타 등) — 컬럼 동기화 전에도 메뉴/API 권한 일치
    from ..database import PRIMARY_ADMIN_EMAILS

    uname = user.username.strip().lower()
    if uname in {e.lower() for e in PRIMARY_ADMIN_EMAILS}:
        return True
    settings = get_settings()
    admins = {
        a.strip().lower()
        for a in settings.admin_usernames.split(",")
        if a.strip()
    }
    return uname in admins
