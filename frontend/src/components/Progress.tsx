import { useEffect, useState } from 'react'
import { api, formatTokens } from '../services/api'
import type { LlmActivity } from '../types/api'

/**
 * Long local-model operations need honest feedback: on a CPU machine the model
 * spends the first minutes reading the documents before a single word appears.
 * This shows which phase is running, how long it has been going and - from
 * llama-server's own progress reports - how much of the prompt has been read,
 * how much was reused from the cache, and about how long the rest will take.
 */
export function Progress({ phase, hint, since, live = true }: { phase: string; hint?: string; since?: number; live?: boolean }) {
  const [now, setNow] = useState(() => Date.now())
  const [start] = useState(() => since ?? Date.now())
  const activity = useActivity(live)

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(t)
  }, [])

  const seconds = Math.max(0, Math.round((now - (since ?? start)) / 1000))
  const reading = activity && (activity.phase === 'reading' || activity.phase === 'waiting') && activity.prompt_total
  return (
    <div className="progress" role="status" aria-live="polite">
      <div className="progress-row">
        <span className="spinner" />
        <span className="phase">{phase}</span>
        {hint && <span className="muted">{hint}</span>}
        <span className="elapsed">{format(seconds)}</span>
      </div>
      {activity && <ActivityLine a={activity} />}
      {reading && (
        <div className="meter thin" aria-hidden="true"><span style={{ width: `${activity.prompt_percent ?? 0}%` }} /></div>
      )}
    </div>
  )
}

function ActivityLine({ a }: { a: LlmActivity }) {
  const parts: string[] = []
  if (a.phase === 'waiting') parts.push('waiting for llama-server')
  if ((a.phase === 'reading' || a.phase === 'waiting') && a.prompt_total) {
    parts.push(`read ${formatTokens(a.prompt_processed)} of ${formatTokens(a.prompt_total)} prompt tokens (${a.prompt_percent ?? 0} %)`)
    if (a.reading_eta_seconds != null && a.reading_eta_seconds > 2) parts.push(`about ${format(a.reading_eta_seconds)} left`)
  }
  if (a.prompt_cached > 0) parts.push(`${formatTokens(a.prompt_cached)} reused from the previous request`)
  if (a.phase === 'thinking') parts.push(`thinking · ${formatTokens(a.thinking_tokens)} tokens`)
  if (a.phase === 'writing') parts.push(`${formatTokens(a.generated_tokens)} of at most ${formatTokens(a.max_tokens)} tokens written`)
  if (!parts.length) return null
  return <div className="progress-detail tiny">{parts.join(' · ')}</div>
}

/** Polls what llama-server is doing while a request runs (the newest request). */
function useActivity(enabled: boolean): LlmActivity | null {
  const [activity, setActivity] = useState<LlmActivity | null>(null)
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    const poll = () => api.llmActivity()
      .then((r) => { if (!cancelled) setActivity(r.active[0] ?? null) })
      .catch(() => { /* the backend is busy or offline: keep the last state */ })
    void poll()
    const t = setInterval(poll, 1000)
    return () => { cancelled = true; clearInterval(t) }
  }, [enabled])
  return activity
}

function format(s: number): string {
  s = Math.round(s)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}

/** Phase label for a streaming answer: reading happens before the first token. */
export function streamPhase(hasFirstToken: boolean): { phase: string; hint: string } {
  return hasFirstToken
    ? { phase: 'Writing the answer', hint: 'streaming from the local model' }
    : { phase: 'Reading your documents', hint: 'the model processes the prompt before it can answer' }
}
