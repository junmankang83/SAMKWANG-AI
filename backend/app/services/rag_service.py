from pathlib import Path
import hashlib
import logging
from typing import List, Tuple

from ..config import Settings, resolved_documents_dir
from .openai_service import embed_documents, extract_text_from_image, generate_chat_completion
from .vector_store import VectorStore, load_vector_store

logger = logging.getLogger(__name__)

# 질문 키워드 → RAG 우선 폴더 (불량 > 규정 > 그 외 knowledge)
_FAILURE_KEYWORDS = (
    "불량",
    "불량품",
    "결함",
    "defect",
    "디펙",
    "양불",
    "수율",
    "불량률",
)
_RULES_KEYWORDS = (
    "규정",
    "내규",
    "사규",
    "취업규칙",
    "복무규정",
    "복무",
    "징계",
    "징계규정",
    "휴가규정",
    "인사규정",
    "윤리규정",
    "취업 규칙",
    "휴가 규정",
    "징계 절차",
)

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


def _rel_path_for_document(path: Path, documents_root: Path) -> str:
    try:
        rel = path.resolve().relative_to(documents_root.resolve())
    except ValueError:
        logger.warning("문서 경로가 documents_root 밖입니다: %s (root=%s)", path, documents_root)
        return ""
    return rel.as_posix().replace("\\", "/").lower()


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
    documents_root: Path,
) -> tuple[list[str], int]:
    """
    파일 내용을 청크로 저장하고 임베딩을 붙인다.
    반환: (chunk doc_key 목록, 청크 수)
    """
    base = _build_doc_key(path)
    stat = path.stat()
    rel_path = _rel_path_for_document(path, documents_root)
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
                "rel_path": rel_path,
                "size": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "content_hash": _build_hash(ch),
            },
            embedding=embedding,
        )
    return keys, len(chunks)


def purge_stored_vectors_for_file(path: Path, settings: Settings) -> None:
    """디스크에서 파일을 지운 뒤에도 호출 가능. resolve() 기준 doc_key로 벡터 스토어 청크를 제거한다."""
    key = _build_doc_key(path)
    store = load_vector_store(settings.vector_db_path)
    _clear_file_chunks_from_store(store, key)


def ingest_document(path: Path, settings: Settings) -> None:
    content = _read_document_content(path)
    if not content.strip():
        logger.info("RAG 인덱싱 건너뜀 (미지원/빈 파일): %s", path.name)
        return

    documents_root = resolved_documents_dir(settings)
    store = load_vector_store(settings.vector_db_path)
    base = _build_doc_key(path)
    _clear_file_chunks_from_store(store, base)
    keys, n = _upsert_path_chunks(path, content, settings, store, documents_root)
    logger.info("RAG 인덱싱 %s: 청크 %s개 (keys=%s)", path.name, n, len(keys))


def sync_documents_folder(settings: Settings) -> dict:
    """
    document 폴더 전체를 스캔해 벡터 스토어를 동기화한다.
    """

    doc_dir = resolved_documents_dir(settings)
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
        keys, n_chunks = _upsert_path_chunks(path, content, settings, store, doc_dir)
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


def rag_scope_rel_path_prefixes(query: str, settings: Settings) -> list[str]:
    """질문에 맞는 document 하위 폴더 접두사 1개를 반환(리스트)."""
    q = (query or "").strip()
    ql = q.lower()
    for kw in _FAILURE_KEYWORDS:
        if kw in q or kw.lower() in ql:
            return [settings.rag_failure_subdir]
    for kw in _RULES_KEYWORDS:
        if kw in q or kw.lower() in ql:
            return [settings.rag_rules_subdir]
    return [settings.rag_knowledge_subdir]


def rag_scope_label(query: str, settings: Settings) -> str:
    prefs = rag_scope_rel_path_prefixes(query, settings)
    if prefs[0].strip().lower() == settings.rag_failure_subdir.strip().lower():
        return "불량 백과(failure encyclopedia)"
    if prefs[0].strip().lower() == settings.rag_rules_subdir.strip().lower():
        return "회사 규정(companyrule)"
    return "일반 지식(knowledge)"


def retrieve_matches_for_chat(
    query: str,
    settings: Settings,
    k: int = 5,
) -> tuple[list[tuple[str, dict]], str]:
    """
    스코프 폴더 우선 검색 후 결과가 부족하면 전체 스토어로 보충한다.
    """
    store = load_vector_store(settings.vector_db_path)
    scope_label = rag_scope_label(query, settings)
    prefixes = rag_scope_rel_path_prefixes(query, settings)
    primary = store.similarity_search(query, k=k, rel_path_prefixes=prefixes)
    if len(primary) >= k:
        return primary[:k], scope_label

    seen: set[str] = set()
    for _c, m in primary:
        dk = str(m.get("doc_key", ""))
        if dk:
            seen.add(dk)

    need = k - len(primary)
    if need <= 0:
        return primary, scope_label

    filler = store.similarity_search(query, k=k * 2, rel_path_prefixes=None)
    merged = list(primary)
    for c, m in filler:
        dk = str(m.get("doc_key", ""))
        if dk and dk in seen:
            continue
        if dk:
            seen.add(dk)
        merged.append((c, m))
        if len(merged) >= k:
            break
    return merged[:k], scope_label


def answer_question(query: str, conversation_id: str | None, model: str, settings: Settings) -> Tuple[str, List[str]]:
    matches, scope_label = retrieve_matches_for_chat(query, settings, k=5)
    if matches:
        context = "\n---\n".join(doc for doc, _meta in matches)
    else:
        context = "No context available."

    prompt = (
        f"Conversation: {conversation_id or 'new'}\n\n"
        f"검색 우선 영역: {scope_label}\n\n"
        f"Context:\n{context}\n\nQuestion:\n{query}"
    )
    print(f"[RAG Service] 요청된 모델: {model}")
    answer = generate_chat_completion(prompt, model=model)
    references = [meta.get("filename", "unknown") for _doc, meta in matches]
    return answer, references

