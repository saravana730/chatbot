from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID


@dataclass
class RetrievedChunk:
    chunk_id: Optional[UUID]
    qdrant_point_id: str
    document_id: UUID
    filename: str
    page_number: Optional[int]
    chunk_index: int
    content: str
    score: float = 0.0
    source: str = "fusion"  # semantic | bm25 | fusion | rerank

    def citation_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "filename": self.filename,
            "page": self.page_number,
            "chunk_index": self.chunk_index,
            "qdrant_point_id": self.qdrant_point_id,
            "score": round(self.score, 4),
            "snippet": self.content[:240],
        }


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    insufficient: bool = False
    query_used: str = ""
    reason: str = ""
    candidate_count: int = 0
    scoped_filenames: list[str] = field(default_factory=list)
