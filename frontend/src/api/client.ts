import type {
  ChatMessage,
  DocumentItem,
  DocumentStatusOut,
  DocumentSummaryOut,
  FAQ,
  IngestBriefingOut,
  SessionItem,
  User,
} from './types'

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  const method = (init.method || 'GET').toUpperCase()
  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = getCookie('csrf_token')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(path, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = data.detail || JSON.stringify(data)
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : 'Request failed')
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  login: (email: string, password: string) =>
    request<User>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ detail: string }>('/auth/logout', { method: 'POST' }),
  me: () => request<User>('/auth/me'),
  listDocuments: () => request<DocumentItem[]>('/documents'),
  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentItem>('/documents/upload', { method: 'POST', body: form })
  },
  documentStatus: (id: string) => request<DocumentStatusOut>(`/documents/${id}/status`),
  documentSummary: (id: string) => request<DocumentSummaryOut>(`/documents/${id}/summary`),
  documentFaqs: (id: string) =>
    request<{ document_id: string; faqs: FAQ[] }>(`/documents/${id}/faqs`),
  deleteDocument: (id: string) =>
    request<{ detail: string }>(`/documents/${id}`, { method: 'DELETE' }),
  listSessions: () => request<SessionItem[]>('/sessions'),
  createSession: (title?: string) =>
    request<SessionItem>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  deleteSession: (id: string) =>
    request<{ detail: string }>(`/sessions/${id}`, { method: 'DELETE' }),
  listMessages: (id: string) => request<ChatMessage[]>(`/sessions/${id}/messages`),
  postIngestBriefing: (sessionId: string, documentId: string) =>
    request<ChatMessage>(`/sessions/${sessionId}/ingest-briefing`, {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId }),
    }),
  postIngestBriefingToLatest: (documentId: string) =>
    request<IngestBriefingOut>('/sessions/ingest-briefing', {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId }),
    }),
}

export type ChatStreamHandlers = {
  onStatus?: (stage: string, message?: string) => void
  onSources?: (sources: unknown[]) => void
  onToken?: (content: string) => void
  onDone?: (messageId: string) => void
  onError?: (detail: string) => void
}

export async function streamChat(
  sessionId: string,
  message: string,
  documentIds: string[] | undefined,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const csrf = getCookie('csrf_token')
  if (csrf) headers['X-CSRF-Token'] = csrf

  const res = await fetch(`/sessions/${sessionId}/chat`, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: JSON.stringify({ message, document_ids: documentIds }),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      const lines = part.split('\n')
      let event = 'message'
      let data = ''
      for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      try {
        const parsed = JSON.parse(data)
        if (event === 'status') handlers.onStatus?.(parsed.stage, parsed.message)
        else if (event === 'sources') handlers.onSources?.(parsed.sources || [])
        else if (event === 'token') handlers.onToken?.(parsed.content || '')
        else if (event === 'done') handlers.onDone?.(parsed.message_id)
        else if (event === 'error') handlers.onError?.(parsed.detail || 'Error')
      } catch {
        /* ignore malformed chunk */
      }
    }
  }
}
