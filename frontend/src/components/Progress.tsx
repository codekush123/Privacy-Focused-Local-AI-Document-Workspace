import { useEffect, useState } from 'react'

/**
 * Long local-model operations need honest feedback: on a CPU machine the model
 * spends the first minute reading the documents before a single word appears.
 * This shows which phase is running and how long it has been going.
 */
export function Progress({ phase, hint, since }: { phase: string; hint?: string; since?: number }) {
  const [now, setNow] = useState(Date.now())
  const start = since ?? now

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(t)
  }, [])

  const seconds = Math.max(0, Math.round((now - start) / 1000))
  return (
    <div className="progress" role="status" aria-live="polite">
      <span className="spinner" />
      <span className="phase">{phase}</span>
      {hint && <span className="muted">{hint}</span>}
      <span className="elapsed">{format(seconds)}</span>
    </div>
  )
}

function format(s: number): string {
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}

/** Phase label for a streaming answer: reading happens before the first token. */
export function streamPhase(hasFirstToken: boolean): { phase: string; hint: string } {
  return hasFirstToken
    ? { phase: 'Writing the answer', hint: 'streaming from the local model' }
    : { phase: 'Reading your documents', hint: 'the model processes the prompt before it can answer' }
}
