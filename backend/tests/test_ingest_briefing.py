from app.services.session_service import _is_ingest_brief


def test_is_ingest_brief_detects_marker():
    assert _is_ingest_brief(
        [{"kind": "ingest_brief", "document_id": "x", "filename": "a.pdf", "faqs": []}]
    )
    assert not _is_ingest_brief([{"document_id": "x", "filename": "a.pdf"}])
    assert not _is_ingest_brief(None)
    assert not _is_ingest_brief([])
