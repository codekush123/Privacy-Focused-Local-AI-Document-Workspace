import type { Citation } from '../types/api'

/** Splits <think>…</think> reasoning (emitted by some models) from the visible answer. */
export function splitThinking(content: string): { thinking: string | null; answer: string } {
  const start = content.indexOf('<think>')
  if (start < 0) return { thinking: null, answer: content }
  const end = content.indexOf('</think>')
  if (end < 0) return { thinking: content.slice(start + 7), answer: '' }
  return { thinking: content.slice(start + 7, end).trim(), answer: (content.slice(0, start) + content.slice(end + 8)).trim() }
}

/**
 * Turns "[S1: Page 3]" markers into Markdown links with a `cite:<index>` href.
 * ChatPanel maps those links to clickable chips that open the SourceViewer.
 */
export function markCitations(text: string, citations: Citation[] | undefined): string {
  if (!citations?.length) return text
  let out = text
  citations.forEach((c, idx) => {
    out = out.split(c.marker).join(`[${c.marker.slice(1, -1)}](cite:${idx})`)
  })
  return out
}
