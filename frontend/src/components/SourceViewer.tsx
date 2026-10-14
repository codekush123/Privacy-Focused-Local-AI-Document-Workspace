import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../services/api'
import { bestEvidence, passageBlocks } from '../services/text'
import type { Citation, DocSection } from '../types/api'
import { Modal } from './Modal'

/**
 * Modal that shows the exact source passage behind a citation. When the cited
 * statement is known, the paragraph or table row it most likely comes from is
 * highlighted and scrolled into view - on a long page that is the difference
 * between checking a claim and searching for it.
 */
export function SourceViewer({ citation, statement, onClose }: {
  citation: Citation
  /** The words of the answer that cite this passage (or a quote to look for). */
  statement?: string
  onClose: () => void
}) {
  const [sections, setSections] = useState<DocSection[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const marked = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!citation.document_id) { setError('This citation points to a source that is not selected.'); return }
    api.documentSections(citation.document_id).then(setSections).catch((e) => setError((e as Error).message))
  }, [citation])

  const section = sections?.find((s) => s.section_id === citation.section_id)
  const blocks = useMemo(() => (section ? passageBlocks(section.markdown) : []), [section])
  const evidence = useMemo(() => (section && statement ? bestEvidence(section.markdown, statement) : null), [section, statement])

  useEffect(() => { marked.current?.scrollIntoView({ block: 'center' }) }, [evidence])

  return (
    <Modal onClose={onClose} label="Cited passage">
      <header className="row between">
        <div>
          <strong>{citation.document_name ?? 'Unknown source'}</strong>
          <span className="muted small"> · {citation.resolved_locator ?? citation.locator}</span>
        </div>
        <button className="btn small" onClick={onClose}>Close</button>
      </header>
      {error && <div className="notice error small">{error}</div>}
      {!error && !sections && <div className="muted small">Loading…</div>}
      {sections && !section && (
        <div className="notice error small">
          The model cited “{citation.locator}”, but no matching section exists in this document. Treat this claim with care.
        </div>
      )}
      {section && (
        <div className="source-passage">
          <div className="muted small">
            Cited passage ({section.locator}) – this is the text the model relied on
            {evidence ? '; the highlighted part shares the most words and numbers with the cited statement.' : '.'}
          </div>
          {statement && <div className="cited-statement small">“{statement}”</div>}
          <div className="bubble">
            {blocks.map((block, i) => {
              const here = evidence?.block === i
              return (
                <div key={i} ref={here ? marked : undefined} className={here && evidence.row == null ? 'evidence' : undefined}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={here && evidence.row != null ? highlightRow(evidence.row) : undefined}>
                    {block}
                  </ReactMarkdown>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </Modal>
  )
}

/** Marks one body row of a Markdown table (row 0 = first row under the header). */
function highlightRow(row: number): Components {
  // In the block's source the header is line 1 and the --- rule line 2.
  return {
    tr: ({ node, ...props }) => (
      <tr {...props} className={node?.position?.start.line === row + 3 ? 'evidence-row' : undefined} />
    ),
  }
}
