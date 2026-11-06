import type { ReactNode } from 'react'
import type { ChatMessage, Citation, IngestBriefCitation } from '../api/types'
import { relevantCitations } from '../lib/citations'
import MarkdownMessage from './MarkdownMessage'

type LiveAssistant = {
  content: string
  citations: Citation[]
  status?: string
}

type Props = {
  messages: ChatMessage[]
  live?: LiveAssistant | null
  onAskFaq?: (question: string) => void
}

function CitationList({
  content,
  citations,
}: {
  content: string
  citations?: Citation[] | null
}) {
  const real = relevantCitations(content, citations)
  if (!real.length) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {real.map((c, i) => (
        <span
          key={`${c.document_id}-${c.page}-${c.ref ?? i}`}
          className="rounded-full border border-line bg-sky/70 px-2.5 py-1 text-[11px] text-navy"
          title={c.snippet || undefined}
        >
          {c.ref != null ? `[${c.ref}] ` : ''}
          {c.filename}
          {c.page != null ? ` · p.${c.page}` : ''}
        </span>
      ))}
    </div>
  )
}

function TypingDots() {
  return (
    <span className="typing-dots inline-flex items-center" aria-label="Assistant is thinking">
      <span />
      <span />
      <span />
    </span>
  )
}

function getIngestBrief(citations?: Citation[] | null): IngestBriefCitation | null {
  const first = citations?.[0]
  if (first && first.kind === 'ingest_brief') {
    return first as IngestBriefCitation
  }
  return null
}

const MENTION_RE = /@([^@\n]+?\.(?:pdf|png|jpe?g|tiff?|txt))/gi

function MentionChip({ name, dark }: { name: string; dark?: boolean }) {
  return (
    <span
      className={`mx-0.5 inline-flex max-w-full items-center align-middle rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        dark
          ? 'bg-white/15 text-white ring-1 ring-white/25'
          : 'bg-sky text-navy ring-1 ring-blue/20'
      }`}
    >
      <span className="truncate">@{name}</span>
    </span>
  )
}

function renderWithMentionChips(text: string, dark?: boolean) {
  const nodes: ReactNode[] = []
  let last = 0
  const re = new RegExp(MENTION_RE.source, 'gi')
  let match: RegExpExecArray | null
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(<span key={`t-${last}`}>{text.slice(last, match.index)}</span>)
    }
    nodes.push(<MentionChip key={`m-${match.index}`} name={match[1]} dark={dark} />)
    last = match.index + match[0].length
  }
  if (last < text.length) {
    nodes.push(<span key={`t-${last}`}>{text.slice(last)}</span>)
  }
  return nodes.length ? nodes : text
}

function IngestBriefCard({
  content,
  brief,
  onAskFaq,
}: {
  content: string
  brief: IngestBriefCitation
  onAskFaq?: (question: string) => void
}) {
  const summaryOnly = content.split(/\n\n\*\*Follow-up FAQs\*\*/)[0]

  return (
    <div className="space-y-3">
      <div className="leading-relaxed">
        <MarkdownMessage content={summaryOnly} />
      </div>
      {brief.faqs?.length > 0 && (
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
            Follow-up FAQs
          </p>
          {brief.faqs.slice(0, 2).map((faq, i) => (
            <div key={i} className="rounded-xl bg-ice/80 p-3 ring-1 ring-line">
              <p className="font-semibold text-navy">{faq.question}</p>
              <p className="mt-1 text-muted">{faq.answer}</p>
              {onAskFaq && (
                <button
                  type="button"
                  onClick={() => onAskFaq(faq.question)}
                  className="mt-2 text-xs font-semibold text-blue hover:text-navy"
                >
                  Ask this →
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function MessageList({ messages, live, onAskFaq }: Props) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-8">
      {!messages.length && !live && (
        <div className="animate-rise py-16 text-center">
          <p className="font-display text-5xl text-navy md:text-6xl">DocChat</p>
          <h2 className="mt-4 font-display text-2xl text-ink md:text-3xl">Ask your documents</h2>
          <p className="mx-auto mt-3 max-w-md text-muted">
            Upload English documents on the left, then ask in English. Use @filename to focus on
            one source.
          </p>
        </div>
      )}

      {messages.map((m) => {
        const brief = m.role === 'assistant' ? getIngestBrief(m.citations) : null
        return (
          <div
            key={m.id}
            className={`animate-rise max-w-[92%] ${m.role === 'user' ? 'self-end' : 'self-start'}`}
          >
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
              {m.role === 'user' ? 'You' : 'Assistant'}
            </p>
            <div
              className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                m.role === 'user'
                  ? 'whitespace-pre-wrap bg-navy text-white'
                  : 'border border-line bg-white text-ink'
              }`}
            >
              {brief ? (
                <IngestBriefCard content={m.content} brief={brief} onAskFaq={onAskFaq} />
              ) : m.role === 'user' ? (
                <span className="whitespace-pre-wrap">
                  {renderWithMentionChips(m.content, true)}
                </span>
              ) : (
                <>
                  <MarkdownMessage content={m.content} />
                  <CitationList content={m.content} citations={m.citations} />
                </>
              )}
            </div>
          </div>
        )
      })}

      {live && (
        <div className="animate-rise max-w-[95%] self-start">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
            Assistant
          </p>
          <div className="rounded-2xl border border-line bg-white px-4 py-3 text-sm leading-relaxed text-ink shadow-sm">
            {!live.content && (
              <p className="flex items-center gap-2 text-muted">
                <TypingDots />
                <span>{live.status || 'Thinking…'}</span>
              </p>
            )}

            {live.content && <MarkdownMessage content={live.content} streaming />}

            <CitationList content={live.content} citations={live.citations} />
          </div>
        </div>
      )}
    </div>
  )
}
