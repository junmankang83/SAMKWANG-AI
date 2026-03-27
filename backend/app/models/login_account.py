"""
PostgreSQL 등 DB의 `login` 테이블과 매핑.
회원가입 시 이메일(아이디) + 비밀번호 해시 저장.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from ..database import Base


class LoginAccount(Base):
    __tablename__ = "login"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    last_login = Column(DateTime, nullable=True)
    login_attempts = Column(Integer, default=0, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def user_id(self) -> int:
        return int(self.id)

    @property
    def username(self) -> str:
        """JWT·응답 필드 호환용(값은 이메일)."""
        return self.email
