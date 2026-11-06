from uuid import uuid4

from app.rag.prompt_builder import build_chat_messages
from app.rag.types import RetrievedChunk


def _chunk(filename: str, content: str, idx: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=None,
        qdrant_point_id=str(uuid4()),
        document_id=uuid4(),
        filename=filename,
        page_number=1,
        chunk_index=idx,
        content=content,
        score=0.5,
        source="fusion",
    )


def test_multi_qa_scope_not_singular_only():
    msgs = build_chat_messages(
        question="What is the premium?",
        chunks=[_chunk("A.pdf", "Premium 100"), _chunk("B.pdf", "Premium 200")],
        history=[],
        insufficient=False,
        scoped_filenames=["A.pdf", "B.pdf"],
        intent="qa",
    )
    user = msgs[-1].content
    assert "scoped files" in user.lower() or "these files" in user.lower()
    assert "Answer that document only" not in user


def test_compare_prompt_asks_for_table():
    msgs = build_chat_messages(
        question="compare A and B",
        chunks=[_chunk("A.pdf", "Covered"), _chunk("B.pdf", "Excluded")],
        history=[],
        insufficient=False,
        scoped_filenames=["A.pdf", "B.pdf"],
        intent="compare",
    )
    user = msgs[-1].content
    assert "Compare" in user or "comparison" in user.lower()
    assert "### A.pdf" in user
    assert "### B.pdf" in user


def test_summarize_prompt_sections_per_file():
    msgs = build_chat_messages(
        question="summarize each",
        chunks=[_chunk("A.pdf", "Summary A"), _chunk("B.pdf", "Summary B")],
        history=[],
        insufficient=False,
        scoped_filenames=["A.pdf", "B.pdf"],
        intent="summarize",
    )
    user = msgs[-1].content
    assert "summary section" in user.lower() or "Summarize" in user
    assert "### A.pdf" in user
