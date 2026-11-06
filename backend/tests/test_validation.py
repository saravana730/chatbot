import pytest

from app.ingestion.validation import FileValidationError, sha256_hex, validate_upload


def test_validate_txt():
    data = b"Hello world\n\nSecond paragraph."
    file_type, mime = validate_upload("notes.txt", "text/plain", data, 10_000)
    assert file_type == "txt"
    assert mime == "text/plain"


def test_validate_pdf_magic():
    data = b"%PDF-1.4 fake content"
    file_type, mime = validate_upload("doc.pdf", "application/pdf", data, 10_000)
    assert file_type == "pdf"
    assert mime == "application/pdf"


def test_reject_bad_extension():
    with pytest.raises(FileValidationError):
        validate_upload("evil.exe", "application/octet-stream", b"MZ", 10_000)


def test_reject_oversized():
    with pytest.raises(FileValidationError):
        validate_upload("notes.txt", "text/plain", b"x" * 100, 50)


def test_sha256_stable():
    assert sha256_hex(b"abc") == sha256_hex(b"abc")
    assert sha256_hex(b"abc") != sha256_hex(b"abd")
