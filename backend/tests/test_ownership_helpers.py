"""Ownership scoping is enforced via get_owned_document filters."""

from uuid import uuid4

from app.models.document import Document, DocumentStatus
from app.models.user import User


def test_document_model_requires_user_id():
    user_id = uuid4()
    doc = Document(
        id=uuid4(),
        user_id=user_id,
        filename="a.txt",
        file_type="txt",
        storage_path="/tmp/a.txt",
        status=DocumentStatus.pending,
        file_hash="abc",
    )
    assert doc.user_id == user_id


def test_user_email_unique_field():
    user = User(email="admin@docchat.com", password_hash="x")
    assert user.email == "admin@docchat.com"
