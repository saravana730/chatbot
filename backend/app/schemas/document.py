from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.document import DocumentStatus, JobStatus


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    file_hash: str
    error_message: Optional[str] = None
    progress_stage: Optional[str] = None
    progress_detail: Optional[str] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    progress_percent: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentStatusOut(BaseModel):
    document_id: UUID
    status: DocumentStatus
    job_status: Optional[JobStatus] = None
    progress_stage: Optional[str] = None
    progress_detail: Optional[str] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    progress_percent: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DocumentSummaryOut(BaseModel):
    document_id: UUID
    summary: str
    created_at: datetime


class DocumentFAQOut(BaseModel):
    id: UUID
    question: str
    answer: str

    model_config = {"from_attributes": True}


class DocumentFAQsOut(BaseModel):
    document_id: UUID
    faqs: list[DocumentFAQOut] = Field(default_factory=list)
