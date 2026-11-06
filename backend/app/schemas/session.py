from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    citations: Optional[list[Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    document_ids: Optional[list[UUID]] = None


class IngestBriefingRequest(BaseModel):
    document_id: UUID


class IngestBriefingOut(BaseModel):
    session: SessionOut
    message: MessageOut
