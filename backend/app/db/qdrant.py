from functools import lru_cache
from typing import Any, Optional
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import get_settings


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection() -> None:
    settings = get_settings()
    client = get_qdrant_client()
    names = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in names:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(
                size=settings.embedding_dim,
                distance=qmodels.Distance.COSINE,
            ),
        )
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="user_id",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="document_id",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="document_status",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )


def upsert_chunks(
    points: list[qmodels.PointStruct],
) -> None:
    settings = get_settings()
    ensure_collection()
    client = get_qdrant_client()
    client.upsert(collection_name=settings.qdrant_collection, points=points)


def delete_document_points(document_id: UUID, user_id: UUID) -> None:
    settings = get_settings()
    client = get_qdrant_client()
    names = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in names:
        return
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=str(document_id)),
                    ),
                    qmodels.FieldCondition(
                        key="user_id",
                        match=qmodels.MatchValue(value=str(user_id)),
                    ),
                ]
            )
        ),
    )


def build_point(
    point_id: str,
    vector: list[float],
    *,
    user_id: UUID,
    document_id: UUID,
    page_number: Optional[int],
    chunk_index: int,
    document_status: str,
    text: str,
) -> qmodels.PointStruct:
    payload: dict[str, Any] = {
        "user_id": str(user_id),
        "document_id": str(document_id),
        "page_number": page_number,
        "chunk_index": chunk_index,
        "document_status": document_status,
        "text": text,
    }
    return qmodels.PointStruct(id=point_id, vector=vector, payload=payload)
