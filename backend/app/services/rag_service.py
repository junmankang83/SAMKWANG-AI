from pathlib import Path
import hashlib
import logging
from typing import List, Tuple

from ..config import Settings
from .openai_service import embed_documents, extract_text_from_image, generate_chat_completion
from .vector_store import VectorStore, load_vector_store

logger = logging.getLogger(__name__)

# RAG 청크 크기(문자). 긴 문서는 여러 청크로 나눠 검색·임베딩한다.
RAG_CHUNK_CHARS = 2000

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".log",
    ".xml",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _read_document_content(path: Path) -> str:
    """
    문서 내용을 텍스트로 읽는다.
    지원되지 않는 바이너리 파일은 빈 문자열로 반환한다.
    """

    if not path.is_file():
        return ""

    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return extract_text_from_image(path)
    if suffix not in TEXT_EXTENSIONS:
        return ""

    raw = path.read_bytes()
    for encoding in ("utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def _build_doc_key(path: Path) -> str:
    return str(path.resolve())


def _build_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _chunk_text(text: str, max_chars: int = RAG_CHUNK_CHARS) -> list[str]:
    t = text.strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]
    return [t[i : i + max_chars] for i in range(0, len(t), max_chars)]


def _clear_file_chunks_from_store(store: VectorStore, base_doc_key: str) -> None:
    """동일 파일의 이전 청크(또는 레거시 단일 doc_key)를 제거한다."""
    before = len(store._documents)
    store._documents = [
        d
        for d in store._documents
        if d.get("metadata", {}).get("base_doc_key") != base_doc_key
        and d.get("metadata", {}).get("doc_key") != base_doc_key
    ]
    if len(store._documents) != before:
        store.persist()


def _upsert_path_chunks(
    path: Path,
    content: str,
    settings: Settings,
    store: VectorStore,
) -> tuple[list[str], int]:
    """
    파일 내용을 청크로 저장하고 임베딩을 붙인다.
    반환: (chunk doc_key 목록, 청크 수)
    """
    base = _build_doc_key(path)
    stat = path.stat()
    chunks = _chunk_text(content)
    if not chunks:
        return [], 0

    keys: list[str] = []
    try:
        emb_list = embed_documents(chunks)
    except Exception:
        logger.exception("청크 임베딩 배치 실패: %s", path.name)
        emb_list = []

    for i, ch in enumerate(chunks):
        doc_key = f"{base}#chunk_{i}"
        keys.append(doc_key)
        emb = emb_list[i] if emb_list and i < len(emb_list) else None
        embedding = (
            emb
            if emb and any(abs(x) > 1e-12 for x in emb)
            else None
        )
        store.upsert_document(
            content=ch,
            metadata={
                "doc_key": doc_key,
                "base_doc_key": base,
                "chunk_index": i,
                "filename": path.name,
                "size": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "content_hash": _build_hash(ch),
            },
            embedding=embedding,
        )
    return keys, len(chunks)


def ingest_document(path: Path, settings: Settings) -> None:
    content = _read_document_content(path)
    if not content.strip():
        logger.info("RAG 인덱싱 건너뜀 (미지원/빈 파일): %s", path.name)
        return

    store = load_vector_store(settings.vector_db_path)
    base = _build_doc_key(path)
    _clear_file_chunks_from_store(store, base)
    keys, n = _upsert_path_chunks(path, content, settings, store)
    logger.info("RAG 인덱싱 %s: 청크 %s개 (keys=%s)", path.name, n, len(keys))


def sync_documents_folder(settings: Settings) -> dict:
    """
    document 폴더 전체를 스캔해 벡터 스토어를 동기화한다.
    """

    doc_dir = Path(settings.documents_path)
    doc_dir.mkdir(parents=True, exist_ok=True)
    store = load_vector_store(settings.vector_db_path)

    indexed_chunks = 0
    indexed_files = 0
    skipped = 0
    doc_keys: set[str] = set()

    for path in sorted(doc_dir.rglob("*")):
        if not path.is_file():
            continue
        content = _read_document_content(path)
        if not content.strip():
            skipped += 1
            continue
        keys, n_chunks = _upsert_path_chunks(path, content, settings, store)
        if not keys:
            skipped += 1
            continue
        doc_keys.update(keys)
        indexed_chunks += n_chunks
        indexed_files += 1

    store.prune_documents(valid_doc_keys=doc_keys)
    return {
        "indexed": indexed_chunks,
        "indexed_files": indexed_files,
        "skipped": skipped,
    }


def answer_question(query: str, conversation_id: str | None, model: str, settings: Settings) -> Tuple[str, List[str]]:
    store = load_vector_store(settings.vector_db_path)
    matches = store.similarity_search(query, k=5)
    if matches:
        context = "\n---\n".join(doc for doc, _meta in matches)
    else:
        context = "No context available."

    prompt = f"Conversation: {conversation_id or 'new'}\n\nContext:\n{context}\n\nQuestion:\n{query}"
    print(f"[RAG Service] 요청된 모델: {model}")
    answer = generate_chat_completion(prompt, model=model)
    references = [meta.get("filename", "unknown") for _doc, meta in matches]
    return answer, references

