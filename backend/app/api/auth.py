"""
회원가입·로그인·내 정보
회원가입은 PostgreSQL/SQLite의 `login` 테이블에 이메일(아이디)로 저장한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import engine, ensure_login_admin_column_and_seed, get_db
from ..deps import get_current_user
from ..models.login_account import LoginAccount
from ..models.schemas import MeResponse, Token, UserLogin, UserSignup
from ..models.user import User
from ..services.auth_service import (
    create_access_token,
    get_login_by_email,
    get_user_by_username,
    hash_password,
    resolve_is_admin,
    verify_password,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _safe_ensure_login_admin_seed() -> None:
    """로그인 성공 후에도 DB 시드 실패 시 500 이 나지 않도록 격리."""
    try:
        ensure_login_admin_column_and_seed(engine)
    except Exception:
        logger.exception("ensure_login_admin_column_and_seed 실패(로그인은 유지됩니다)")


@router.post("/auth/signup", response_model=Token)
def signup(payload: UserSignup, db: Session = Depends(get_db)):
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")
    if get_login_by_email(db, str(payload.email)):
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")

    row = LoginAccount(
        email=str(payload.email).strip().lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    # login.is_admin 시드(지정 이메일만 True). 직후 ORM과 동기화.
    _safe_ensure_login_admin_seed()
    db.refresh(row)

    token = create_access_token(row.email)
    return Token(
        access_token=token,
        username=row.email,
        is_admin=resolve_is_admin(row),
    )


@router.post("/auth/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    account = get_login_by_email(db, str(payload.email))
    if account and verify_password(payload.password, account.password_hash):
        if account.is_locked:
            raise HTTPException(status_code=403, detail="잠긴 계정입니다.")
        account.last_login = datetime.now(timezone.utc)
        account.login_attempts = 0
        db.commit()
        _safe_ensure_login_admin_seed()
        db.refresh(account)
        token = create_access_token(account.email)
        return Token(
            access_token=token,
            username=account.email,
            is_admin=resolve_is_admin(account),
        )

    # 기존 users 테이블 계정(구버전) 호환: 아이디가 이메일이 아닌 경우
    user = get_user_by_username(db, str(payload.email))
    if user and verify_password(payload.password, user.password_hash):
        if user.is_locked:
            raise HTTPException(status_code=403, detail="잠긴 계정입니다.")
        user.last_login = datetime.now(timezone.utc)
        user.login_attempts = 0
        db.commit()
        _safe_ensure_login_admin_seed()
        token = create_access_token(user.username)
        return Token(
            access_token=token,
            username=user.username,
            is_admin=resolve_is_admin(user),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="아이디(이메일) 또는 비밀번호가 올바르지 않습니다.",
    )


@router.get("/auth/me", response_model=MeResponse)
def me(user: User | LoginAccount = Depends(get_current_user)):
    return MeResponse(
        user_id=user.user_id,
        username=user.username,
        is_admin=resolve_is_admin(user),
    )
