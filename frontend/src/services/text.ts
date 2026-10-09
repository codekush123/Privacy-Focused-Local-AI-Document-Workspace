import { defaultUrlTransform } from 'react-markdown'
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

/**
 * URL filter for ReactMarkdown that keeps the app's own `cite:<index>` links (and the
 * `flag:<index>` marks of numbers the answer check could not find in the sources).
 * react-markdown's default filter blanks every unknown scheme (a safety measure
 * against `javascript:` links), which turned citation chips into empty links that
 * opened a blank tab. Every other URL still goes through the default filter.
 */
export function citationUrlTransform(url: string): string {
  return /^(cite|flag):\d+$/.test(url) ? url : defaultUrlTransform(url)
}

/**
 * Wraps numbers the answer check could not find in the sources as `flag:<i>`
 * links, which the chat renders as highlighted marks. Digits that belong to a
 * longer number or to a citation link are left alone.
 */
export function markUnsupportedNumbers(text: string, numbers: string[] | undefined): string {
  if (!numbers?.length) return text
  let out = text
  numbers.forEach((token, idx) => {
    const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+')
    const re = new RegExp(`(?<![\\d.,\\w])${escaped}(?![\\d\\w]|[.,]\\d)(?![^\\[]*\\]\\(cite:)`, 'g')
    out = out.replace(re, (m) => `[${m}](flag:${idx})`)
  })
  return out
}
