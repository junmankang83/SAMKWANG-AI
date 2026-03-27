"""
데이터베이스 초기화 스크립트
사용자 테이블 생성
"""
from .database import engine, Base
from .models.user import User


def init_db():
    """
    데이터베이스 테이블 생성
    """
    Base.metadata.create_all(bind=engine)
    print("데이터베이스 테이블이 생성되었습니다.")


if __name__ == "__main__":
    init_db()


