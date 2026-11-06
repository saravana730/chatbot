import type { Citation } from '../api/types'

const REF_RE = /[\[【]\s*(\d+)\s*[\]】]/g

export function extractCitedRefs(content: string): Set<number> {
  const refs = new Set<number>()
  const re = new RegExp(REF_RE.source, 'g')
  let match: RegExpExecArray | null
  while ((match = re.exec(content)) !== null) {
    refs.add(Number(match[1]))
  }
  return refs
}

/** Prefer citations the answer actually references; fall back to stored list. */
export function relevantCitations(
  content: string,
  citations?: Citation[] | null,
): Citation[] {
  const real = (citations || []).filter((c) => c.kind !== 'ingest_brief')
  if (!real.length) return []

  const refs = extractCitedRefs(content)
  let used = refs.size
    ? real.filter((c) => c.ref != null && refs.has(c.ref))
    : []

  // Older messages may lack ref — match by [n] position in list
  if (!used.length && refs.size) {
    used = real.filter((_, i) => refs.has(i + 1))
  }

  if (!used.length) {
    const lower = content.toLowerCase()
    used = real.filter((c) => {
      const name = (c.filename || '').toLowerCase()
      return name && (lower.includes(name) || lower.includes(name.replace(/\.[^.]+$/, '')))
    })
  }

  // Deduplicate chips by document + page
  const seen = new Set<string>()
  const out: Citation[] = []
  for (const c of used) {
    const key = `${c.document_id}|${c.page ?? ''}|${c.chunk_index ?? ''}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(c)
  }
  return out
}
