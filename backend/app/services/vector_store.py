"""
로컬 파일 기반의 단순 벡터 스토어 래퍼.
실제 서비스에서는 Chroma/FAISS 등을 사용해야 한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import List, Tuple


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


@dataclass
class VectorStore:
    storage_path: Path
    _documents: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.storage_path = self._resolve_storage_file(self.storage_path)
        if self.storage_path.exists():
            try:
                self._documents = json.loads(self.storage_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._documents = []

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def persist(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self._documents, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_document(self, content: str, metadata: dict) -> None:
        self._documents.append({"content": content, "metadata": metadata})
        self.persist()

    def upsert_document(
        self,
        content: str,
        metadata: dict,
        key: str = "doc_key",
        embedding: list[float] | None = None,
    ) -> None:
        """
        metadata[key] 값을 기준으로 기존 문서를 갱신하거나 새로 추가한다.
        """

        target_key = metadata.get(key)
        if target_key is None:
            doc: dict = {"content": content, "metadata": metadata}
            if embedding is not None:
                doc["embedding"] = embedding
            self._documents.append(doc)
            self.persist()
            return

        for item in self._documents:
            item_key = item.get("metadata", {}).get(key)
            if item_key == target_key:
                item["content"] = content
                item["metadata"] = metadata
                if embedding is not None:
                    item["embedding"] = embedding
                else:
                    item.pop("embedding", None)
                self.persist()
                return

        new_item: dict = {"content": content, "metadata": metadata}
        if embedding is not None:
            new_item["embedding"] = embedding
        self._documents.append(new_item)
        self.persist()

    def prune_documents(self, valid_doc_keys: set[str], key: str = "doc_key") -> None:
        """
        현재 폴더에 없는 문서를 스토어에서 제거한다.
        """

        original = len(self._documents)
        self._documents = [
            item
            for item in self._documents
            if item.get("metadata", {}).get(key) in valid_doc_keys
        ]
        if len(self._documents) != original:
            self.persist()

    @staticmethod
    def _normalize_rel_prefixes(prefixes: list[str]) -> list[str]:
        out: list[str] = []
        for p in prefixes:
            n = str(p).strip().replace("\\", "/").lower().strip("/")
            if n:
                out.append(n + "/")
        return out

    @staticmethod
    def metadata_matches_rel_prefixes(metadata: dict, normalized_prefixes: list[str]) -> bool:
        """rel_path 가 없는 레거시 청크는 필터 시 제외."""
        rp = str(metadata.get("rel_path") or "").replace("\\", "/").lower()
        if not rp:
            return False
        for pfx in normalized_prefixes:
            if rp.startswith(pfx):
                return True
        return False

    def _candidate_documents(
        self,
        rel_path_prefixes: list[str] | None,
    ) -> list[dict]:
        if rel_path_prefixes is None:
            return self._documents
        np = self._normalize_rel_prefixes(rel_path_prefixes)
        if not np:
            return self._documents
        return [
            d
            for d in self._documents
            if self.metadata_matches_rel_prefixes(d.get("metadata", {}), np)
        ]

    def _similarity_search_tokens(
        self,
        query: str,
        k: int,
        candidate_docs: list[dict] | None = None,
    ) -> List[Tuple[str, dict]]:
        docs = candidate_docs if candidate_docs is not None else self._documents
        query_tokens = self._tokenize(query)
        if not query_tokens:
            fallback = sorted(
                docs,
                key=lambda item: item.get("metadata", {}).get("modified_ns", 0),
                reverse=True,
            )
            return [
                (item.get("content", ""), item.get("metadata", {}))
                for item in fallback[:k]
                if item.get("content", "").strip()
            ]

        scored: list[tuple[int, str, dict]] = []
        for doc in docs:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            content_lower = content.lower()
            score = 0
            for token in query_tokens:
                if token in content_lower:
                    score += 1
            if score > 0:
                scored.append((score, content, metadata))

        if not scored:
            fallback = sorted(
                docs,
                key=lambda item: item.get("metadata", {}).get("modified_ns", 0),
                reverse=True,
            )
            return [
                (item.get("content", ""), item.get("metadata", {}))
                for item in fallback[:k]
                if item.get("content", "").strip()
            ]

        scored.sort(key=lambda item: item[0], reverse=True)
        return [(content, metadata) for _score, content, metadata in scored[:k]]

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        rel_path_prefixes: list[str] | None = None,
    ) -> List[Tuple[str, dict]]:
        """
        임베딩(있을 때) + 토큰 겹침 폴백/보강.
        rel_path_prefixes: document 루트 기준 상대 경로 접두사(예: ["failure encyclopedia/"]).
        None 이면 전체 스토어.
        """
        q = (query or "").strip()
        candidates = self._candidate_documents(rel_path_prefixes)
        embed_results: List[Tuple[str, dict]] = []
        if q and candidates:
            with_emb = [d for d in candidates if d.get("embedding")]
            if with_emb:
                from .openai_service import embed_query_text

                qvec = embed_query_text(q)
                if qvec and any(abs(x) > 1e-12 for x in qvec):
                    scored: list[tuple[float, str, dict]] = []
                    for doc in candidates:
                        ev = doc.get("embedding")
                        if not ev or len(ev) != len(qvec):
                            continue
                        sim = _cosine_similarity(qvec, ev)
                        scored.append((sim, doc.get("content", ""), doc.get("metadata", {})))
                    scored.sort(key=lambda item: item[0], reverse=True)
                    embed_results = [
                        (c, m) for s, c, m in scored[:k] if s > 0.0
                    ]

        token_results = self._similarity_search_tokens(q, k, candidates)
        if not embed_results:
            return token_results[:k]

        seen_keys: set[str] = set()
        out: List[Tuple[str, dict]] = []
        for c, m in embed_results:
            dk = str(m.get("doc_key", ""))
            if dk and dk not in seen_keys:
                seen_keys.add(dk)
                out.append((c, m))
        for c, m in token_results:
            dk = str(m.get("doc_key", ""))
            key = dk if dk else str(id(m))
            if key not in seen_keys:
                seen_keys.add(key)
                out.append((c, m))
            if len(out) >= k:
                break
        return out[:k]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [tok for tok in re.findall(r"[0-9A-Za-z가-힣_]+", text.lower()) if len(tok) > 1]

    @staticmethod
    def _resolve_storage_file(path: Path) -> Path:
        """
        전달된 경로가 디렉터리면 내부 store.json 파일을 사용한다.
        """

        if path.exists() and path.is_dir():
            return path / "store.json"
        if not path.suffix:
            return path / "store.json"
        return path


def load_vector_store(path: str) -> VectorStore:
    return VectorStore(storage_path=Path(path))

