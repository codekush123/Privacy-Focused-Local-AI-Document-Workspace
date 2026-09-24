import type { Citation } from '../types/api'

/** Splits <think>…</think> reasoning (emitted by some models) from the visible answer. */
export function splitThinking(content: string): { thinking: string | null; answer: string } {
  const start = content.indexOf('<think>')
  if (start < 0) return { thinking: null, answer: content }
  const end = content.indexOf('</think>')
  if (end < 0) return { thinking: content.slice(start + 7), answer: '' }
  return { thinking: content.slice(start + 7, end).trim(), answer: (content.slice(0, start) + content.slice(end + 8)).trim() }
}

const MARKDOWN_CITATION = /\[([^\]\n]{1,400})\]\(\s*(S\d+[^)\n]{0,80}?)\s*\)/g

/**
 * Repairs the Markdown-link citation shape some models produce:
 * `[the F1 score is ...](S1: Page 3)` becomes `the F1 score is ... [S1: Page 3]`.
 * Mirrors normalize_citations() in the backend so what is displayed and what was
 * parsed into chips agree.
 */
export function normalizeCitations(text: string): string {
  return text.replace(MARKDOWN_CITATION, '$1 [$2]')
}

/**
 * Turns "[S1: Page 3]" markers into Markdown links with a `cite:<index>` href.
 * ChatPanel maps those links to clickable chips that open the SourceViewer.
 */
export function markCitations(text: string, citations: Citation[] | undefined): string {
  const normalized = normalizeCitations(text)
  if (!citations?.length) return normalized
  let out = normalized
  citations.forEach((c, idx) => {
    out = out.split(c.marker).join(`[${c.marker.slice(1, -1)}](cite:${idx})`)
  })
  return out
}
