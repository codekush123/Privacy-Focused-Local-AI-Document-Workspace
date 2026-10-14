import type { AnswerCheck } from '../types/api'

const CHECK_LOOK: Record<AnswerCheck['status'], { icon: string; tone: string; label: string }> = {
  ok: { icon: '✓', tone: 'good', label: 'Answer check passed' },
  partly_cited: { icon: '✓', tone: 'good', label: 'Answer check: numbers verified' },
  review: { icon: '⚠', tone: 'warn', label: 'Answer check: please review' },
  not_in_documents: { icon: 'ⓘ', tone: 'plain', label: 'Answer check' },
  no_sources: { icon: '', tone: 'plain', label: '' },
}

/** Live answer check: numbers, citations and refusals checked against the sources, no model call. */
export function AnswerCheckView({ c }: { c: AnswerCheck }) {
  const look = CHECK_LOOK[c.status]
  const hasDetails = c.unsupported_numbers.length > 0 || c.uncited_sentences.length > 0 || c.unresolved_citations.length > 0
  return (
    <details className={`answer-check ${look.tone}`}>
      <summary>
        <span className={`badge ${look.tone}`}>{look.icon} {look.label}</span>
        <span className="small">{c.summary}</span>
      </summary>
      <div className="small answer-check-body">
        <div className="muted">
          Checked without a second model: {c.numbers_total} number{c.numbers_total === 1 ? '' : 's'},
          {' '}{c.sentences_total} statement{c.sentences_total === 1 ? '' : 's'}, {c.citations_total} citation{c.citations_total === 1 ? '' : 's'}.
        </div>
        {c.unsupported_numbers.length > 0 && (
          <div><strong>Not found in the sources:</strong> {c.unsupported_numbers.map((n) => <mark key={n} className="unsupported-number">{n}</mark>)}
            <span className="muted"> - invented, or calculated by the model. Highlighted in the answer.</span></div>
        )}
        {c.unresolved_citations.length > 0 && (
          <div><strong>Citations that match no section:</strong> {c.unresolved_citations.join(', ')}</div>
        )}
        {c.uncited_sentences.length > 0 && (
          <div><strong>Statements without a citation:</strong>
            <ul>{c.uncited_sentences.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </div>
        )}
        {!hasDetails && <div className="muted">Nothing to review.</div>}
      </div>
    </details>
  )
}
