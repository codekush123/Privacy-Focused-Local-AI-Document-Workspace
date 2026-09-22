import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../services/api'
import type { Citation, DocSection } from '../types/api'

/** Modal that shows the exact source passage behind a citation. */
export function SourceViewer({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const [sections, setSections] = useState<DocSection[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!citation.document_id) { setError('This citation points to a source that is not selected.'); return }
    api.documentSections(citation.document_id).then(setSections).catch((e) => setError((e as Error).message))
  }, [citation])

  const section = sections?.find((s) => s.section_id === citation.section_id)
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
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
            <div className="muted small">Cited passage ({section.locator}) – this is the text the model relied on:</div>
            <div className="bubble"><ReactMarkdown remarkPlugins={[remarkGfm]}>{section.markdown}</ReactMarkdown></div>
          </div>
        )}
      </div>
    </div>
  )
}
