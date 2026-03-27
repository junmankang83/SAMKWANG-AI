"""
데이터베이스 연결 및 세션 관리
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .config import get_settings

settings = get_settings()

# `login` 테이블: 아래 이메일(정규화 소문자)만 is_admin=True. 그 외 계정은 False.
# (구분/오타 도메인 samkwnag.com 을 쓰는 계정도 동일 관리자로 인정)
PRIMARY_ADMIN_EMAILS: tuple[str, ...] = (
    "junman.kang@samkwang.com",
    "junman.kang@samkwnag.com",
)


def ensure_login_admin_column_and_seed(engine) -> None:
    """
    구 DB에 `is_admin` 컬럼이 없으면 추가하고,
    매 기동 시 login 전원 is_admin=False 후 PRIMARY_ADMIN_EMAILS만 True로 맞춘다.
    """
    try:
        inspector = inspect(engine)
    except Exception:
        return
    if "login" not in inspector.get_table_names():
        return
    col_names = {c["name"] for c in inspector.get_columns("login")}
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if "is_admin" not in col_names:
            if dialect == "sqlite":
                conn.execute(
                    text(
                        "ALTER TABLE login ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE login ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false"
                    )
                )
        if dialect == "sqlite":
            conn.execute(text("UPDATE login SET is_admin = 0"))
            for email in PRIMARY_ADMIN_EMAILS:
                conn.execute(
                    text(
                        "UPDATE login SET is_admin = 1 WHERE lower(trim(email)) = :email"
                    ),
                    {"email": email.lower()},
                )
        else:
            conn.execute(text("UPDATE login SET is_admin = false"))
            for email in PRIMARY_ADMIN_EMAILS:
                conn.execute(
                    text(
                        "UPDATE login SET is_admin = true WHERE lower(trim(email)) = :email"
                    ),
                    {"email": email.lower()},
                )

# SQLAlchemy 엔진 생성
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False
)

# 세션 팩토리 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 클래스
Base = declarative_base()


def get_db():
    """
    데이터베이스 세션 의존성
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


