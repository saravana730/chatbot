export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface User {
  id: string
  email: string
  created_at: string
}

export interface DocumentItem {
  id: string
  filename: string
  file_type: string
  status: DocumentStatus
  file_hash: string
  error_message?: string | null
  progress_stage?: string | null
  progress_detail?: string | null
  progress_current?: number | null
  progress_total?: number | null
  progress_percent?: number | null
  created_at: string
  updated_at: string
}

export interface DocumentStatusOut {
  document_id: string
  status: DocumentStatus
  job_status?: string | null
  progress_stage?: string | null
  progress_detail?: string | null
  progress_current?: number | null
  progress_total?: number | null
  progress_percent?: number | null
  error?: string | null
}

export interface DocumentSummaryOut {
  document_id: string
  summary: string
  created_at: string
}

export interface FAQ {
  id: string
  question: string
  answer: string
}

export interface SessionItem {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Citation {
  document_id: string
  filename: string
  page?: number | null
  chunk_index?: number
  score?: number
  snippet?: string
  ref?: number
  kind?: string
  faqs?: FAQ[]
}

export interface IngestBriefCitation {
  kind: 'ingest_brief'
  document_id: string
  filename: string
  faqs: Array<{ question: string; answer: string }>
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | string
  content: string
  citations?: Citation[] | null
  created_at: string
}

export interface IngestBriefingOut {
  session: SessionItem
  message: ChatMessage
}
