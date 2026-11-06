import { useCallback, useEffect, useRef, useState } from 'react'
import { api, streamChat } from '../api/client'
import type { ChatMessage, Citation, DocumentItem, SessionItem, User } from '../api/types'
import ChatComposer from '../components/ChatComposer'
import DocumentSidebar from '../components/DocumentSidebar'
import MessageList from '../components/MessageList'

export default function ChatPage({
  user,
  onLogout,
}: {
  user: User
  onLogout: () => void
}) {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [live, setLive] = useState<{
    content: string
    citations: Citation[]
    status?: string
  } | null>(null)
  const [busy, setBusy] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const sendingRef = useRef(false)
  const prevStatusRef = useRef<Record<string, string>>({})
  const announcingRef = useRef<Set<string>>(new Set())
  const sessionIdRef = useRef<string | null>(null)

  const refreshDocuments = useCallback(async () => {
    const docs = await api.listDocuments()
    setDocuments(docs)
  }, [])

  const refreshSessions = useCallback(async () => {
    const list = await api.listSessions()
    setSessions(list)
  }, [])

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  useEffect(() => {
    void (async () => {
      await Promise.all([refreshDocuments(), refreshSessions()])
    })()
  }, [refreshDocuments, refreshSessions])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, live])

  async function ensureSession(): Promise<string> {
    if (sessionIdRef.current) return sessionIdRef.current
    const created = await api.createSession()
    setSessionId(created.id)
    sessionIdRef.current = created.id
    setSessions((prev) => [created, ...prev])
    return created.id
  }

  const announceReadyDocument = useCallback(async (doc: DocumentItem) => {
    if (announcingRef.current.has(doc.id)) return
    announcingRef.current.add(doc.id)
    try {
      // Always land in the user's most recently active session
      const { session, message } = await api.postIngestBriefingToLatest(doc.id)
      setSessionId(session.id)
      sessionIdRef.current = session.id
      const rows = await api.listMessages(session.id)
      setMessages(rows.some((m) => m.id === message.id) ? rows : [...rows, message])
      setLive(null)
      await refreshSessions()
    } catch {
      announcingRef.current.delete(doc.id)
    }
  }, [refreshSessions])

  // When a document finishes ingesting, push summary + 2 FAQs into latest active chat
  useEffect(() => {
    for (const doc of documents) {
      const prev = prevStatusRef.current[doc.id]
      prevStatusRef.current[doc.id] = doc.status
      if (doc.status !== 'ready') continue
      // Only on transition into ready (not on first paint of already-ready docs)
      if (prev && prev !== 'ready') {
        void announceReadyDocument(doc)
      }
    }
  }, [documents, announceReadyDocument])

  async function openSession(id: string) {
    setSessionId(id)
    sessionIdRef.current = id
    const rows = await api.listMessages(id)
    setMessages(rows)
    setLive(null)
  }

  async function newChat() {
    const created = await api.createSession()
    setSessionId(created.id)
    sessionIdRef.current = created.id
    setMessages([])
    setLive(null)
    setSessions((prev) => [created, ...prev])
  }

  async function handleSend(message: string, documentIds?: string[]) {
    if (sendingRef.current) return
    sendingRef.current = true
    setBusy(true)
    setLive({ content: '', citations: [], status: 'Thinking…' })

    const optimistic: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, optimistic])

    try {
      const sid = await ensureSession()
      let citations: Citation[] = []
      let content = ''

      await streamChat(sid, message, documentIds, {
        onStatus: (_stage, msg) =>
          setLive((prev) => ({
            content: prev?.content || '',
            citations: prev?.citations || [],
            status: msg || 'Working…',
          })),
        onSources: (sources) => {
          citations = sources as Citation[]
          setLive((prev) => ({
            content: prev?.content || '',
            citations,
            status: prev?.status,
          }))
        },
        onToken: (token) => {
          content += token
          setLive({ content, citations, status: undefined })
        },
        onDone: async () => {
          const rows = await api.listMessages(sid)
          setMessages(rows)
          setLive(null)
          await refreshSessions()
        },
        onError: (detail) => {
          setLive({
            content: content || detail,
            citations,
            status: undefined,
          })
        },
      })
    } catch (err) {
      setLive({
        content: err instanceof Error ? err.message : 'Chat failed',
        citations: [],
      })
    } finally {
      setBusy(false)
      sendingRef.current = false
    }
  }

  async function logout() {
    try {
      await api.logout()
    } catch {
      /* ignore */
    }
    onLogout()
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <div
        className={`${sidebarOpen ? 'w-[340px]' : 'w-0'} hidden shrink-0 overflow-hidden transition-all duration-300 md:block`}
      >
        <div className="flex h-full w-[340px] flex-col">
          <DocumentSidebar
            documents={documents}
            onRefresh={refreshDocuments}
            onUploaded={refreshDocuments}
          />
          <div className="border-t border-line bg-white/80 px-4 py-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
                Recent chats
              </p>
              <button
                type="button"
                onClick={() => void newChat()}
                className="text-xs font-semibold text-blue hover:text-navy"
              >
                New
              </button>
            </div>
            <ul className="max-h-40 space-y-1 overflow-y-auto">
              {sessions.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => void openSession(s.id)}
                    className={`w-full truncate rounded-lg px-2 py-1.5 text-left text-xs transition ${
                      sessionId === s.id
                        ? 'bg-sky font-semibold text-navy'
                        : 'text-muted hover:bg-ice hover:text-navy'
                    }`}
                  >
                    {s.title}
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => void logout()}
              className="mt-3 text-xs text-muted hover:text-navy"
            >
              Sign out · {user.email}
            </button>
          </div>
        </div>
      </div>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line bg-white/75 px-4 py-3 backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-lg border border-line px-2 py-1 text-xs text-navy md:hidden"
              onClick={() => setSidebarOpen((v) => !v)}
            >
              Docs
            </button>
            <div>
              <p className="font-display text-xl text-navy md:hidden">DocChat</p>
              <p className="text-sm text-muted">
                English docs · ask across files, or scope with @
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void newChat()}
            className="rounded-xl bg-blue px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-navy"
          >
            New chat
          </button>
        </header>

        <div className="flex-1 overflow-y-auto">
          <MessageList
            messages={messages}
            live={live}
            onAskFaq={(q) => void handleSend(q)}
          />
          <div ref={bottomRef} />
        </div>

        <ChatComposer
          documents={documents}
          disabled={busy}
          onSend={(m, ids) => void handleSend(m, ids)}
        />
      </main>
    </div>
  )
}
