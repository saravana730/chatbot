from app.ingestion.chunker import chunk_document, count_tokens
from app.ingestion.types import ContentBlock, ExtractedDocument, ExtractedPage


def _doc_from_paragraphs(paragraphs: list[str]) -> ExtractedDocument:
    blocks = [
        ContentBlock(text=p, kind="paragraph", page_number=1, reading_order=i)
        for i, p in enumerate(paragraphs)
    ]
    return ExtractedDocument(
        pages=[ExtractedPage(page_number=1, blocks=blocks, source="text")],
        filename="sample.txt",
        file_type="txt",
    )


def test_count_tokens_positive():
    assert count_tokens("hello world") > 0


def test_chunking_preserves_page_and_index(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "chunk_size", 50)
    monkeypatch.setattr(config.get_settings(), "chunk_overlap", 10)

    paragraphs = [
        "Heading one content about policy coverage and duration. " * 5,
        "Another paragraph with claims process details and contacts. " * 5,
        "Final section describing exclusions and waiting periods. " * 5,
    ]
    chunks = chunk_document(_doc_from_paragraphs(paragraphs))
    assert len(chunks) >= 2
    assert chunks[0].chunk_index == 0
    assert all(c.page_number == 1 for c in chunks)
    assert all(c.content.strip() for c in chunks)


def test_heading_attached_to_following_paragraph():
    doc = ExtractedDocument(
        pages=[
            ExtractedPage(
                page_number=2,
                blocks=[
                    ContentBlock(text="Coverage Period", kind="heading", page_number=2, reading_order=0),
                    ContentBlock(
                        text="The policy covers twelve months from inception.",
                        kind="paragraph",
                        page_number=2,
                        reading_order=1,
                    ),
                ],
                source="native",
            )
        ],
        filename="policy.pdf",
        file_type="pdf",
    )
    chunks = chunk_document(doc)
    assert len(chunks) == 1
    assert "Coverage Period" in chunks[0].content
    assert chunks[0].page_number == 2
