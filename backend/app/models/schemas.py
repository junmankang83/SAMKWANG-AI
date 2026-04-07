from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="사용자 메시지")
    conversation_id: Optional[str] = None
    model: Optional[str] = "gpt-3.5-turbo"
    rag_folder: Optional[str] = Field(
        default=None,
        description="document 하위 폴더 상대경로. 유효한 값일 때만 해당 폴더 RAG. 생략·빈 문자열·null 은 「자동」= 문서 검색 없이 LLM 일반 답변",
    )

    @field_validator("rag_folder", mode="before")
    @classmethod
    def _normalize_rag_folder(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        s = v.strip().replace("\\", "/").strip("/")
        return s if s else None


class ChatResponse(BaseModel):
    answer: str
    references: List[str] = Field(default_factory=list)


class DocumentIngestResponse(BaseModel):
    filename: str
    size: int


# 인증 관련 스키마
class UserSignup(BaseModel):
    """회원가입: 아이디는 이메일 형식만 허용. DB `login` 테이블에 저장."""

    email: EmailStr
    password: str = Field(..., min_length=6, description="비밀번호(최소 6자)")
    password_confirm: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool = False


class MeResponse(BaseModel):
    user_id: int
    username: str
    is_admin: bool


class UserResponse(BaseModel):
    user_id: int
    username: str
    last_login: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

