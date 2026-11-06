/** Human-friendly ingest phases for overall progress UI. */
export const INGEST_PHASES = [
  { id: 'reading', label: 'Reading', stages: ['queued', 'starting', 'extracting', 'ocr'] },
  { id: 'understanding', label: 'Understanding', stages: ['normalizing', 'summarizing', 'faqs'] },
  { id: 'indexing', label: 'Indexing', stages: ['chunking', 'embedding', 'indexing'] },
  { id: 'ready', label: 'Ready', stages: ['ready'] },
] as const

const STAGE_TO_PHASE: Record<string, string> = {}
for (const phase of INGEST_PHASES) {
  for (const s of phase.stages) STAGE_TO_PHASE[s] = phase.id
}

export function resolveIngestStage(stage?: string | null, status?: string): string {
  if (status === 'ready' || stage === 'ready') return 'ready'
  if (status === 'failed' || stage === 'failed') return 'failed'
  if (stage && STAGE_TO_PHASE[stage]) return stage
  if (status === 'processing') return 'starting'
  return 'queued'
}

function phaseForStage(stage: string): string {
  if (stage === 'failed') return 'reading'
  return STAGE_TO_PHASE[stage] || 'reading'
}

function phaseLabel(stage: string): string {
  const id = phaseForStage(stage)
  return INGEST_PHASES.find((p) => p.id === id)?.label || 'Processing'
}

type Props = {
  stage?: string | null
  status?: string
  detail?: string | null
  current?: number | null
  total?: number | null
  percent?: number | null
  failed?: boolean
  done?: boolean
}

export default function ProcessStepper({
  stage,
  status,
  detail,
  current,
  total,
  percent,
  failed,
  done,
}: Props) {
  const resolved = resolveIngestStage(stage, status)
  const activePhase = phaseForStage(resolved)
  const pct = done
    ? 100
    : failed
      ? Math.min(percent ?? 0, 99)
      : Math.max(0, Math.min(100, percent ?? 0))

  const unitLabel =
    total && total > 0 && current != null
      ? resolved === 'embedding' || resolved === 'chunking' || resolved === 'indexing'
        ? `Passage ${current} of ${total}`
        : resolved === 'summarizing'
          ? `Section ${current} of ${total}`
          : `Page ${current} of ${total}`
      : null

  return (
    <div className="w-full space-y-2 py-1">
      <div className="flex items-center justify-between gap-2">
        <p className={`text-[11px] font-semibold ${failed ? 'text-danger' : 'text-navy'}`}>
          {failed ? 'Failed' : done ? 'Ready' : phaseLabel(resolved)}
        </p>
        <p className="text-[11px] font-semibold tabular-nums text-blue">{pct}%</p>
      </div>

      <div
        className="h-2 overflow-hidden rounded-full bg-line"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Document processing progress"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-out ${
            failed ? 'bg-danger' : 'bg-gradient-to-r from-blue to-blue-bright'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {(unitLabel || detail) && (
        <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
          {unitLabel && (
            <p className="text-[11px] font-semibold tabular-nums text-navy">{unitLabel}</p>
          )}
          {detail && (
            <p className={`text-[10px] ${failed ? 'text-danger' : 'text-muted'}`}>{detail}</p>
          )}
        </div>
      )}

      {!done && !failed && (
        <ol className="flex gap-1 pt-0.5">
          {INGEST_PHASES.filter((p) => p.id !== 'ready').map((phase) => {
            const active = phase.id === activePhase
            const phaseIdx = INGEST_PHASES.findIndex((p) => p.id === phase.id)
            const activeIdx = INGEST_PHASES.findIndex((p) => p.id === activePhase)
            const complete = phaseIdx < activeIdx
            return (
              <li
                key={phase.id}
                className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${
                  active
                    ? 'bg-sky text-blue ring-1 ring-blue/25'
                    : complete
                      ? 'bg-blue/10 text-navy'
                      : 'bg-white text-muted ring-1 ring-line'
                }`}
              >
                {phase.label}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

/** @deprecated kept for imports that still reference step lists */
export const INGEST_STEPS = INGEST_PHASES.map((p) => ({ id: p.id, label: p.label }))
