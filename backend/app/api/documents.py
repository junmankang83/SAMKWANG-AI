"""
문서 폴더 동기화·업로드·목록·다운로드
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import Settings, get_settings, resolved_documents_dir
from ..deps import require_admin
from ..models.login_account import LoginAccount
from ..models.user import User
from ..services.rag_service import ingest_document, purge_stored_vectors_for_file, sync_documents_folder

router = APIRouter()

# 문서 검색·등록 UI 목록에서만 제외(디스크·RAG 인덱스에는 그대로 둠)
_EXCLUDED_FROM_DOCUMENT_LIST_NAMES: frozenset[str] = frozenset(
    {"curl_test.txt", "README.md"}
)


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
    folders: list[str] = Field(
        default_factory=list,
        description="document 기준 하위 디렉터리 상대 경로(파일 없는 빈 폴더 포함)",
    )


class UploadResponse(BaseModel):
    filename: str
    path: str
    size: int
    documents_path: str


class CreateFolderBody(BaseModel):
    """document 기준 하위 폴더 경로(중첩은 슬래시)."""

    relative_path: str = Field(..., min_length=1, description="예: 보고서 또는 회계/2024")


class CreateFolderResponse(BaseModel):
    path: str
    documents_path: str


class DeleteItemResponse(BaseModel):
    path: str
    kind: str  # "file" | "directory"


def _doc_dir(settings: Settings) -> Path:
    root = resolved_documents_dir(settings)
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_default_document_subdirs(doc_dir: Path, settings: Settings) -> None:
    """RAG 설정의 1단계 하위 폴더가 없으면 생성해 목록·업로드 UI에 항상 나타나게 한다."""
    root = doc_dir.resolve()
    for attr in ("rag_failure_subdir", "rag_knowledge_subdir", "rag_rules_subdir"):
        raw = getattr(settings, attr, None)
        if raw is None:
            continue
        name = str(raw).strip().replace("\\", "/").strip("/")
        if not name or ".." in Path(name).parts:
            continue
        dest = (root / name).resolve()
        try:
            dest.relative_to(root)
        except ValueError:
            continue
        dest.mkdir(parents=True, exist_ok=True)


def _collect_folder_rels(doc_dir: Path, doc_infos: list[DocumentInfo]) -> list[str]:
    """디스크 walk + 파일 경로의 상위 디렉터리로 폴더 목록을 모은다."""
    root = doc_dir.resolve()
    found: set[str] = set()
    if root.is_dir():
        for dirpath, _dirnames, _filenames in os.walk(root):
            sub = Path(dirpath)
            try:
                rel = sub.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel != ".":
                found.add(rel)
    for d in doc_infos:
        parent = Path(d.path).parent
        if parent == Path("."):
            continue
        parts = [p for p in parent.as_posix().split("/") if p]
        for i in range(len(parts)):
            found.add("/".join(parts[: i + 1]))
    return sorted(found)


def _normalize_subfolder(folder: str) -> str:
    """multipart folder 값 → document 기준 상대 경로(파일명 제외). 빈 문자열이면 루트."""
    s = (folder or "").strip().replace("\\", "/").strip("/")
    if not s:
        return ""
    parts = [p for p in s.split("/") if p]
    for p in parts:
        if p in (".", "..") or p.startswith(".."):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="폴더 경로에 허용되지 않은 구성 요소가 있습니다.",
            )
    return "/".join(parts)


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
        documents_path=str(resolved_documents_dir(settings)),
    )


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    folder: str = Form(""),
    _: Union[User, LoginAccount] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """
    관리자만: 파일을 document 폴더(또는 하위 folder)에 저장하고 RAG 인덱스에 반영한다.
    """
    doc_dir = _doc_dir(settings)
    raw_name = file.filename or "unnamed"
    name = Path(raw_name).name
    if not name or name in (".", "..") or "/" in raw_name or "\\" in raw_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="파일명만 허용됩니다(하위 경로 불가).",
        )
    sub = _normalize_subfolder(folder)
    relative_posix = f"{sub}/{name}" if sub else name
    dest = _safe_target_under_doc_dir(doc_dir, relative_posix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()
    size = dest.stat().st_size
    ingest_document(dest, settings)
    return UploadResponse(
        filename=name,
        path=relative_posix,
        size=size,
        documents_path=str(doc_dir),
    )


@router.post("/documents/folder", response_model=CreateFolderResponse)
def create_document_folder(
    body: CreateFolderBody,
    _: Union[User, LoginAccount] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """관리자만: document 아래에 빈 폴더(중첩 가능)를 만든다."""
    doc_dir = _doc_dir(settings)
    rel = _normalize_subfolder(body.relative_path)
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="폴더 경로를 입력하세요.",
        )
    target = _safe_target_under_doc_dir(doc_dir, rel)
    if target.exists():
        if target.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="같은 경로에 파일이 있어 폴더를 만들 수 없습니다.",
            )
        return CreateFolderResponse(path=rel, documents_path=str(doc_dir))
    target.mkdir(parents=True, exist_ok=False)
    return CreateFolderResponse(path=rel, documents_path=str(doc_dir))


@router.get("/documents/list", response_model=DocumentListResponse)
def list_documents(
    _: Union[User, LoginAccount] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """관리자만: document 폴더 내 파일 목록 및 하위 폴더 경로(빈 폴더 포함)."""
    doc_dir = _doc_dir(settings)
    ensure_default_document_subdirs(doc_dir, settings)
    docs: list[DocumentInfo] = []
    for p in sorted(doc_dir.rglob("*")):
        if p.is_file():
            if p.name in _EXCLUDED_FROM_DOCUMENT_LIST_NAMES:
                continue
            rel = p.relative_to(doc_dir).as_posix()
            docs.append(
                DocumentInfo(
                    path=rel,
                    name=p.name,
                    size=p.stat().st_size,
                )
            )
    folder_rels = _collect_folder_rels(doc_dir, docs)
    return DocumentListResponse(
        documents=docs,
        documents_path=str(doc_dir),
        folders=folder_rels,
    )


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


@router.delete("/documents/item", response_model=DeleteItemResponse)
def delete_document_item(
    path: str = Query(..., min_length=1, description="document 기준 상대 경로(파일 또는 빈 폴더)"),
    _: Union[User, LoginAccount] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """관리자만: 파일 삭제(RAG 청크 제거) 또는 비어 있는 폴더만 삭제."""
    doc_dir = _doc_dir(settings)
    rel = path.strip().replace("\\", "/").strip("/")
    if not rel or ".." in Path(rel).parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="잘못된 경로입니다.")
    target = _safe_target_under_doc_dir(doc_dir, rel)
    if not target.exists():
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")

    if target.is_file():
        target.unlink()
        purge_stored_vectors_for_file(target, settings)
        return DeleteItemResponse(path=rel, kind="file")

    if target.is_dir():
        try:
            if any(target.iterdir()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="폴더 안에 파일이나 하위 폴더가 있어 삭제할 수 없습니다.",
                )
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="폴더 내용을 확인할 수 없습니다.",
            ) from exc
        try:
            target.rmdir()
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="폴더를 삭제할 수 없습니다. 비어 있는 폴더만 삭제할 수 있습니다.",
            ) from exc
        return DeleteItemResponse(path=rel, kind="directory")

    raise HTTPException(status_code=400, detail="파일 또는 폴더만 삭제할 수 있습니다.")
