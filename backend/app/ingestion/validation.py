import hashlib
from pathlib import Path
from typing import Optional

ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
}

MAGIC_SIGNATURES = {
    b"%PDF": "application/pdf",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
}


class FileValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def detect_mime_from_bytes(data: bytes) -> Optional[str]:
    for sig, mime in MAGIC_SIGNATURES.items():
        if data.startswith(sig):
            return mime
    # UTF-8 / ASCII text heuristic
    try:
        data[:4096].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return None


def validate_upload(
    filename: str,
    content_type: Optional[str],
    data: bytes,
    max_bytes: int,
) -> tuple[str, str]:
    if not data:
        raise FileValidationError("Empty file")
    if len(data) > max_bytes:
        raise FileValidationError(f"File exceeds maximum size of {max_bytes} bytes")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(f"Unsupported file extension: {ext}")

    expected_mime = ALLOWED_EXTENSIONS[ext]
    detected = detect_mime_from_bytes(data)

    if ext == ".txt":
        if detected not in (None, "text/plain"):
            # Allow if content is valid text even when magic is wrong
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise FileValidationError("TXT file is not valid UTF-8") from exc
        file_type = "txt"
    else:
        if detected and detected != expected_mime:
            raise FileValidationError(
                f"File signature mismatch: expected {expected_mime}, got {detected}"
            )
        if content_type and content_type.split(";")[0].strip().lower() not in {
            expected_mime,
            "application/octet-stream",
        }:
            # Soft check — signature is authoritative
            pass
        file_type = ext.lstrip(".")
        if file_type == "jpeg":
            file_type = "jpg"
        if file_type == "tif":
            file_type = "tiff"

    return file_type, expected_mime


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
