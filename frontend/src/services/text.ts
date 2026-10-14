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
 * The statement a citation backs: the text between the previous sentence end
 * (or line break) and the marker. Used to find the cited words in the source.
 */
export function citationContext(answer: string, marker: string): string {
  const text = normalizeCitations(answer)
  const at = text.indexOf(marker)
  if (at < 0) return ''
  const before = text.slice(0, at).replace(/\[S\d+[^\]]*\]/g, ' ')
  const statements = before.split(/(?<=[.!?])\s+|\n+/).map((s) => s.trim()).filter(Boolean)
  return (statements.at(-1) ?? '').replace(/[*_`#|>]+/g, ' ').trim()
}

/** Blocks of a Markdown passage, blank-line separated (a table is one block). */
export function passageBlocks(markdown: string): string[] {
  return markdown.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean)
}

const WORD = /[\p{L}\p{N}][\p{L}\p{N}.,]*/gu

function terms(text: string): Set<string> {
  const out = new Set<string>()
  for (const m of text.toLowerCase().matchAll(WORD)) {
    const w = m[0].replace(/[.,]+$/, '')
    // Numbers count in full; words by their first five letters, so Finnish
    // case endings ("tuulipuisto" / "tuulipuistossa") still match.
    if (/\d/.test(w)) out.add(w.replace(/[.,]/g, ''))
    else if (w.length >= 4) out.add(w.slice(0, 5))
  }
  return out
}

/**
 * Where in a passage the cited statement comes from: the block (and, inside a
 * table, the row) sharing the most words and numbers with it. Null when nothing
 * overlaps - then nothing is highlighted rather than something arbitrary.
 */
export function bestEvidence(markdown: string, statement: string): { block: number; row: number | null } | null {
  const wanted = terms(statement)
  if (!wanted.size) return null
  const score = (text: string) => {
    let s = 0
    for (const t of terms(text)) if (wanted.has(t)) s += /\d/.test(t) ? 3 : 1  // a shared number is strong evidence
    return s
  }
  let best: { block: number; row: number | null } | null = null
  let bestScore = 0
  const blocks = passageBlocks(markdown)
  for (let i = 0; i < blocks.length; i++) {
    const lines = blocks[i].split('\n')
    if (lines.length > 2 && lines.every((l) => l.trim().startsWith('|'))) {
      for (let r = 2; r < lines.length; r++) {  // rows after the header and the --- rule
        const s = score(lines[r])
        if (s > bestScore) { best = { block: i, row: r - 2 }; bestScore = s }
      }
    } else {
      const s = score(blocks[i])
      if (s > bestScore) { best = { block: i, row: null }; bestScore = s }
    }
  }
  return best
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
