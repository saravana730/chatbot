from app.rag.citations import (
    extract_cited_refs,
    filter_citations_used_in_answer,
)


def test_extract_ascii_and_fullwidth_refs():
    text = "Premium is QAR 1,000 【1】【3】 and period [2]."
    assert extract_cited_refs(text) == {1, 2, 3}


def test_filter_keeps_only_cited_refs():
    citations = [
        {"ref": 1, "document_id": "a", "filename": "a.pdf", "page": 1, "chunk_index": 0},
        {"ref": 2, "document_id": "b", "filename": "b.pdf", "page": 1, "chunk_index": 0},
        {"ref": 3, "document_id": "a", "filename": "a.pdf", "page": 1, "chunk_index": 1},
    ]
    used = filter_citations_used_in_answer("Answer 【1】【3】", citations)
    assert [c["ref"] for c in used] == [1, 3]


def test_filter_empty_when_no_refs():
    citations = [
        {"ref": 1, "document_id": "a", "filename": "secret.pdf", "page": 1, "chunk_index": 0},
    ]
    assert filter_citations_used_in_answer("No sources here.", citations) == []
