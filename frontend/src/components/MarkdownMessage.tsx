import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type Props = {
  content: string
  streaming?: boolean
}

export default function MarkdownMessage({ content, streaming }: Props) {
  return (
    <div className={`md-body text-sm leading-relaxed text-ink ${streaming ? 'streaming' : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-blue underline">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-xl ring-1 ring-line">
              <table className="min-w-full border-collapse text-left text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-sky/80 text-navy">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b border-line px-3 py-2 font-semibold">{children}</th>
          ),
          td: ({ children }) => (
            <td className="border-b border-line px-3 py-2 align-top text-ink/90">{children}</td>
          ),
          code: ({ className, children }) => {
            const block = Boolean(className)
            if (block) {
              return (
                <code className="block overflow-x-auto rounded-xl bg-ice p-3 text-[12px] text-navy ring-1 ring-line">
                  {children}
                </code>
              )
            }
            return (
              <code className="rounded bg-sky/70 px-1 py-0.5 text-[12px] text-navy">{children}</code>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
      {streaming && <span className="typing-caret" aria-hidden />}
    </div>
  )
}
