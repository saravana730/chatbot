import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import type { DocumentItem } from '../api/types'

type Props = {
  documents: DocumentItem[]
  disabled?: boolean
  onSend: (message: string, documentIds?: string[]) => void
}

export default function ChatComposer({ documents, disabled, onSend }: Props) {
  const [value, setValue] = useState('')
  const [chips, setChips] = useState<DocumentItem[]>([])
  const [suggest, setSuggest] = useState<DocumentItem[]>([])
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const readyDocs = useMemo(
    () => documents.filter((d) => d.status === 'ready'),
    [documents],
  )

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [value])

  function updateSuggestions(text: string) {
    const at = text.match(/@([^\s@]*)$/)
    if (!at) {
      setOpen(false)
      setSuggest([])
      return
    }
    const q = at[1].toLowerCase()
    const selected = new Set(chips.map((c) => c.id))
    const matches = readyDocs
      .filter((d) => !selected.has(d.id) && d.filename.toLowerCase().includes(q))
      .slice(0, 6)
    setSuggest(matches)
    setHighlight(0)
    setOpen(matches.length > 0)
  }

  function addChip(doc: DocumentItem) {
    setChips((prev) => (prev.some((c) => c.id === doc.id) ? prev : [...prev, doc]))
    // Remove trailing @query from the textarea — chip carries the attachment
    setValue((prev) => prev.replace(/@([^\s@]*)$/, '').replace(/\s+$/, ' '))
    setOpen(false)
    setSuggest([])
    textareaRef.current?.focus()
  }

  function removeChip(id: string) {
    setChips((prev) => prev.filter((c) => c.id !== id))
    textareaRef.current?.focus()
  }

  function submit(e?: FormEvent) {
    e?.preventDefault()
    const text = value.trim()
    if ((!text && !chips.length) || disabled) return
    const mentionPrefix = chips.map((c) => `@${c.filename}`).join(' ')
    const message = [mentionPrefix, text].filter(Boolean).join(' ').trim()
    onSend(
      message,
      chips.length ? chips.map((c) => c.id) : undefined,
    )
    setValue('')
    setChips([])
    setOpen(false)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (open && suggest.length) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlight((h) => (h + 1) % suggest.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlight((h) => (h - 1 + suggest.length) % suggest.length)
        return
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault()
        addChip(suggest[highlight])
        return
      }
      if (e.key === 'Escape') {
        setOpen(false)
        return
      }
    }
    if (e.key === 'Backspace' && !value && chips.length) {
      e.preventDefault()
      setChips((prev) => prev.slice(0, -1))
      return
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form
      onSubmit={submit}
      className="relative border-t border-line bg-white/85 px-4 py-3 backdrop-blur"
    >
      {open && (
        <div className="absolute bottom-full left-4 right-4 mb-2 overflow-hidden rounded-xl border border-line bg-white shadow-[0_12px_40px_rgba(11,58,110,0.12)]">
          <p className="border-b border-line px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
            Attach a document
          </p>
          {suggest.map((doc, i) => (
            <button
              key={doc.id}
              type="button"
              className={`block w-full px-3 py-2.5 text-left text-sm ${
                i === highlight ? 'bg-sky text-navy' : 'text-ink hover:bg-ice'
              }`}
              onMouseEnter={() => setHighlight(i)}
              onClick={() => addChip(doc)}
            >
              <span className="font-semibold text-blue">@{doc.filename}</span>
            </button>
          ))}
        </div>
      )}

      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <div className="relative min-w-0 flex-1 rounded-2xl border border-line bg-ice px-3 py-2 transition focus-within:border-blue focus-within:ring-2 focus-within:ring-blue/20">
          {chips.length > 0 && (
            <div className="mb-1.5 flex flex-wrap gap-1.5">
              {chips.map((chip) => (
                <span
                  key={chip.id}
                  className="inline-flex max-w-full items-center gap-1 rounded-full bg-sky px-2.5 py-1 text-[11px] font-semibold text-navy ring-1 ring-blue/20"
                >
                  <span className="truncate">@{chip.filename}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${chip.filename}`}
                    disabled={disabled}
                    onClick={() => removeChip(chip.id)}
                    className="rounded-full px-0.5 text-muted hover:bg-white hover:text-navy"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            disabled={disabled}
            onChange={(e) => {
              setValue(e.target.value)
              updateSuggestions(e.target.value)
            }}
            onKeyDown={onKeyDown}
            placeholder={
              disabled
                ? 'DocChat is answering…'
                : chips.length
                  ? 'Ask, summarize, or compare the attached files…'
                  : 'Ask in English… type @ to attach files'
            }
            className="max-h-36 min-h-[40px] w-full resize-none bg-transparent px-1 py-1.5 text-sm outline-none disabled:cursor-not-allowed disabled:opacity-70"
          />
          {disabled && (
            <span className="pointer-events-none absolute bottom-3 right-3 typing-dots">
              <span />
              <span />
              <span />
            </span>
          )}
        </div>
        <button
          type="submit"
          disabled={disabled || (!value.trim() && !chips.length)}
          className="rounded-2xl bg-blue px-5 py-3.5 text-sm font-semibold text-white shadow-sm transition hover:bg-navy disabled:opacity-45"
        >
          {disabled ? '…' : 'Send'}
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-[11px] text-muted">
        Enter to send · Shift+Enter for new line · @ attaches file chips · compare / summarize works with multiple
      </p>
    </form>
  )
}
