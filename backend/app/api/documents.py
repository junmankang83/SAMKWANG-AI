"""
문서 폴더 동기화·업로드·목록·다운로드
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Union

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..deps import require_admin
from ..models.login_account import LoginAccount
from ..models.user import User
from ..services.rag_service import ingest_document, sync_documents_folder

router = APIRouter()


class SyncResponse(BaseModel):
    indexed: int
    skipped: int
    documents_path: str


class DocumentInfo(BaseModel):
    """document 폴더 기준 상대 경로(하위 폴더 포함)."""

    path: str = Field(description="다운로드 시 동일 path 사용")
    name: str
    size: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]
    documents_path: str


class UploadResponse(BaseModel):
    filename: str
    path: str
    size: int
    documents_path: str


def _doc_dir(settings: Settings) -> Path:
    root = Path(settings.documents_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_target_under_doc_dir(doc_dir: Path, relative_posix: str) -> Path:
    """relative_posix: 'a.txt' 또는 'sub/b.txt' — 디렉터리 탈출 방지."""
    if not relative_posix or relative_posix.startswith("/") or ".." in Path(relative_posix).parts:
        raise HTTPException(status_code=400, detail="잘못된 문서 경로입니다.")
    target = (doc_dir / relative_posix).resolve()
    try:
        target.relative_to(doc_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="허용되지 않은 경로입니다.") from exc
    return target


@router.post("/documents/sync", response_model=SyncResponse)
async def sync_documents(
    _: Union[User, LoginAccount] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """관리자만: documents_path 전체를 스캔해 로컬 벡터 스토어와 동기화한다."""
    stats = sync_documents_folder(settings)
    return SyncResponse(
        indexed=stats["indexed"],
        skipped=stats["skipped"],
        documents_path=str(Path(settings.documents_path).resolve()),
    )


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    _: Union[User, LoginAccount] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """
    관리자만: 파일을 document 폴더에 저장하고 RAG 인덱스에 반영한다.
    """
    doc_dir = _doc_dir(settings)
    raw_name = file.filename or "unnamed"
    name = Path(raw_name).name
    if not name or name in (".", "..") or "/" in raw_name or "\\" in raw_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일명만 허용됩니다(하위 경로 불가).",
        )
    dest = _safe_target_under_doc_dir(doc_dir, name)
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()
    size = dest.stat().st_size
    ingest_document(dest, settings)
    return UploadResponse(
        filename=name,
        path=name,
        size=size,
        documents_path=str(doc_dir),
    )


@router.get("/documents/list", response_model=DocumentListResponse)
def list_documents(
    _: Union[User, LoginAccount] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """관리자만: document 폴더 내 파일 목록."""
    doc_dir = _doc_dir(settings)
    docs: list[DocumentInfo] = []
    for p in sorted(doc_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(doc_dir).as_posix()
            docs.append(
                DocumentInfo(
                    path=rel,
                    name=p.name,
                    size=p.stat().st_size,
                )
            )
    return DocumentListResponse(documents=docs, documents_path=str(doc_dir))


@router.get("/documents/file")
def download_document(
    path: str,
    _: Union[User, LoginAccount] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """관리자만: 저장된 파일 열람·다운로드(쿼리 path=상대 경로)."""
    doc_dir = _doc_dir(settings)
    target = _safe_target_under_doc_dir(doc_dir, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    # 한글 파일명은 헤더 인코딩 이슈가 발생할 수 있어 직접 filename 헤더를 구성하지 않는다.
    # 브라우저에서 Blob URL로 열람하므로 파일 본문만 안정적으로 반환하면 된다.
    return FileResponse(path=target)
