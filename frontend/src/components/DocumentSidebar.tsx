import { useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { api } from '../api/client'
import type { DocumentItem, FAQ } from '../api/types'
import ProcessStepper from './ProcessStepper'

type Props = {
  documents: DocumentItem[]
  onRefresh: () => void
  onUploaded: () => void
}

type UploadEvent = {
  id: string
  filename: string
  phase: 'uploading' | 'queued' | 'done' | 'error'
  message: string
}

export default function DocumentSidebar({ documents, onRefresh, onUploaded }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [summary, setSummary] = useState('')
  const [faqs, setFaqs] = useState<FAQ[]>([])
  const [events, setEvents] = useState<UploadEvent[]>([])
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const pending = documents.filter((d) => d.status === 'pending' || d.status === 'processing')
    if (!pending.length) return
    const t = setInterval(onRefresh, 1500)
    return () => clearInterval(t)
  }, [documents, onRefresh])

  function emit(event: UploadEvent) {
    setEvents((prev) => {
      const rest = prev.filter((e) => e.id !== event.id)
      return [event, ...rest].slice(0, 4)
    })
  }

  async function handleUpload(files: FileList | File[] | null) {
    if (!files || !files.length) return
    const list = Array.from(files)
    for (const file of list) {
      const id = `${file.name}-${Date.now()}`
      emit({ id, filename: file.name, phase: 'uploading', message: 'Uploading file…' })
      try {
        await api.uploadDocument(file)
        emit({ id, filename: file.name, phase: 'queued', message: 'Queued — watching progress below' })
        onUploaded()
        window.setTimeout(() => {
          setEvents((prev) => prev.filter((e) => e.id !== id))
        }, 3500)
      } catch (err) {
        emit({
          id,
          filename: file.name,
          phase: 'error',
          message: err instanceof Error ? err.message : 'Upload failed',
        })
      }
    }
    if (inputRef.current) inputRef.current.value = ''
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    void handleUpload(e.dataTransfer.files)
  }

  async function toggleDetails(doc: DocumentItem) {
    if (expanded === doc.id) {
      setExpanded(null)
      return
    }
    setExpanded(doc.id)
    if (doc.status !== 'ready') {
      setSummary('')
      setFaqs([])
      return
    }
    try {
      const [s, f] = await Promise.all([api.documentSummary(doc.id), api.documentFaqs(doc.id)])
      setSummary(s.summary)
      setFaqs(f.faqs)
    } catch {
      setSummary('Summary not available yet.')
      setFaqs([])
    }
  }

  async function removeDoc(id: string) {
    await api.deleteDocument(id)
    if (expanded === id) setExpanded(null)
    onRefresh()
  }

  return (
    <aside className="flex h-full w-full flex-col border-r border-line bg-white/80 backdrop-blur-sm">
      <div className="border-b border-line px-5 py-4">
        <p className="font-display text-2xl text-navy">DocChat</p>
        <p className="text-xs text-muted">Your English document library</p>
      </div>

      <div className="px-4 py-3">
        <label
          onDragEnter={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragOver={(e) => e.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-3 py-5 text-center transition ${
            dragging
              ? 'border-blue bg-sky scale-[1.01]'
              : 'border-blue/35 bg-ice hover:border-blue hover:bg-sky/60'
          }`}
        >
          <span className="text-sm font-semibold text-navy">Drop files or browse</span>
          <span className="mt-1 text-xs text-muted">
            PDF · PNG · JPG · TIFF · TXT · English text works best
          </span>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.txt"
            onChange={(e) => void handleUpload(e.target.files)}
          />
        </label>

        {events.length > 0 && (
          <ul className="mt-3 space-y-2">
            {events.map((ev) => (
              <li
                key={ev.id}
                className="animate-rise rounded-xl border border-line bg-white px-3 py-2 text-xs shadow-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate font-semibold text-navy">{ev.filename}</p>
                  <span
                    className={
                      ev.phase === 'error'
                        ? 'text-danger'
                        : ev.phase === 'done'
                          ? 'text-ok'
                          : 'text-blue'
                    }
                  >
                    {ev.phase}
                  </span>
                </div>
                <p className="mt-0.5 text-muted">{ev.message}</p>
                {(ev.phase === 'uploading' || ev.phase === 'queued') && (
                  <div className="mt-2 upload-progress">
                    <span />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        <p className="px-2 pb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
          Uploaded files
        </p>
        <ul className="space-y-2">
          {documents.map((doc) => {
            const inFlight = doc.status === 'pending' || doc.status === 'processing'
            return (
              <li key={doc.id} className="rounded-2xl border border-line bg-ice/70 px-3 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <button
                    type="button"
                    className="min-w-0 flex-1 text-left"
                    onClick={() => void toggleDetails(doc)}
                  >
                    <p className="truncate text-sm font-semibold text-navy">{doc.filename}</p>
                    <p className="mt-0.5 text-[11px] text-muted">
                      {doc.status === 'ready'
                        ? 'Ready to chat'
                        : doc.status === 'failed'
                          ? 'Failed'
                          : doc.progress_percent != null
                            ? `${doc.progress_percent}% · ${doc.progress_detail || 'Processing…'}`
                            : doc.progress_detail || 'Processing…'}
                    </p>
                  </button>
                  <button
                    type="button"
                    className="text-[11px] text-muted hover:text-danger"
                    onClick={() => void removeDoc(doc.id)}
                  >
                    Delete
                  </button>
                </div>

                {(inFlight || doc.status === 'failed') && (
                  <div className="mt-2">
                    <ProcessStepper
                      stage={doc.progress_stage}
                      status={doc.status}
                      done={doc.status === 'ready'}
                      failed={doc.status === 'failed'}
                      detail={doc.error_message || undefined}
                      current={doc.progress_current}
                      total={doc.progress_total}
                      percent={doc.progress_percent}
                    />
                  </div>
                )}

                {expanded === doc.id && doc.status === 'ready' && (
                  <div className="mt-2 space-y-2 border-t border-line pt-2 text-xs text-ink/80">
                    <p className="font-semibold text-navy">Summary</p>
                    <p className="leading-relaxed">{summary || 'Loading summary…'}</p>
                    {faqs.map((faq) => (
                      <div key={faq.id} className="rounded-xl bg-white p-2.5 ring-1 ring-line">
                        <p className="font-semibold text-navy">{faq.question}</p>
                        <p className="mt-1 text-muted">{faq.answer}</p>
                      </div>
                    ))}
                  </div>
                )}
              </li>
            )
          })}
          {!documents.length && (
            <li className="px-2 py-8 text-center text-sm text-muted">
              No documents yet — drop a file to begin
            </li>
          )}
        </ul>
      </div>
    </aside>
  )
}
