"""RAG 폴더 스코프 분류 및 rel_path 필터 검색."""

from pathlib import Path
import tempfile

from backend.app.config import Settings
from backend.app.services.rag_service import rag_scope_rel_path_prefixes
from backend.app.services.vector_store import VectorStore


def test_rag_scope_failure_before_rules() -> None:
    s = Settings()
    assert rag_scope_rel_path_prefixes("불량이 규정 위반인가요", s) == [s.rag_failure_subdir]


def test_rag_scope_rules() -> None:
    s = Settings()
    assert rag_scope_rel_path_prefixes("휴가 규정 알려줘", s) == [s.rag_rules_subdir]


def test_rag_scope_knowledge_default() -> None:
    s = Settings()
    assert rag_scope_rel_path_prefixes("회사 소개 요약", s) == [s.rag_knowledge_subdir]


def test_similarity_search_filters_by_rel_path() -> None:
    tmp = Path(tempfile.mkdtemp())
    store_path = tmp / "store.json"
    vs = VectorStore(storage_path=store_path)
    vs._documents = [
        {
            "content": "apple banana cherry",
            "metadata": {
                "doc_key": "k1",
                "rel_path": "knowledge/doc.txt",
                "modified_ns": 1,
            },
        },
        {
            "content": "apple banana date",
            "metadata": {
                "doc_key": "c1",
                "rel_path": "companyrule/rule.txt",
                "modified_ns": 2,
            },
        },
    ]
    results = vs.similarity_search("banana", k=5, rel_path_prefixes=["knowledge"])
    assert len(results) == 1
    assert results[0][1]["rel_path"] == "knowledge/doc.txt"


def test_metadata_matches_rel_prefixes() -> None:
    assert VectorStore.metadata_matches_rel_prefixes(
        {"rel_path": "failure encyclopedia/x.txt"},
        ["failure encyclopedia/"],
    )
    assert not VectorStore.metadata_matches_rel_prefixes(
        {"rel_path": "knowledge/x.txt"},
        ["failure encyclopedia/"],
    )
    assert not VectorStore.metadata_matches_rel_prefixes({}, ["knowledge/"])
