import { useState } from 'react'
import { api, RequestError } from '../services/api'
import type { Citation, DocumentSummary, TimelineEvent, TimelineResult } from '../types/api'
import { Progress } from './Progress'
import { SourceViewer } from './SourceViewer'

interface Props {
  documents: DocumentSummary[]
  selectedIds: string[]
  ready: boolean
  onExportCreated: () => Promise<void>
  notify: (msg: string, kind?: 'error' | 'info') => void
}

const LANGUAGES: { id: string; label: string; locale: string }[] = [
  { id: '', label: 'Language of the documents', locale: 'en-GB' },
  { id: 'English', label: 'English', locale: 'en-GB' },
  { id: 'Finnish', label: 'Suomeksi (Finnish)', locale: 'fi-FI' },
]

const STATUS: Record<TimelineEvent['status'], { label: string; tone: string; hint: string }> = {
  verified: { label: '✓ verified', tone: 'good', hint: 'The date appears next to this event in the cited passage' },
  date_elsewhere: { label: '⚠ date belongs elsewhere', tone: 'warn', hint: 'The date is in the source, but not next to this event' },
  date_not_in_source: { label: '⚠ date not in source', tone: 'warn', hint: 'The cited passage does not contain this date' },
  citation_unresolved: { label: '⚠ no matching source', tone: 'warn', hint: 'The citation does not match a section of the documents' },
  invalid_date: { label: '⚠ unreadable date', tone: 'bad', hint: 'The date could not be read' },
}

function formatDate(e: TimelineEvent, locale: string): string {
  if (e.status === 'invalid_date') return e.date_text || e.date
  const [y, m, d] = e.date.split('-').map(Number)
  const when = new Date(Date.UTC(y, (m || 1) - 1, d || 1))
  const opts: Intl.DateTimeFormatOptions = e.precision === 'day'
    ? { day: 'numeric', month: 'short', year: 'numeric' }
    : e.precision === 'month' ? { month: 'long', year: 'numeric' } : { year: 'numeric' }
  return new Intl.DateTimeFormat(locale, { ...opts, timeZone: 'UTC' }).format(when)
}

/**
 * Timeline of the selected documents: the model lists the dated events, the app
 * checks that each date really appears in the cited passage and sorts them.
 */
export function TimelinePanel({ documents, selectedIds, ready, onExportCreated, notify }: Props) {
  const [language, setLanguage] = useState('')
  const [result, setResult] = useState<TimelineResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [since, setSince] = useState<number | null>(null)
  const [onlyVerified, setOnlyVerified] = useState(false)
  const [docFilter, setDocFilter] = useState<string>('')
  const [openCitation, setOpenCitation] = useState<Citation | null>(null)
  const selectedDocs = documents.filter((d) => selectedIds.includes(d.id))
  const locale = LANGUAGES.find((l) => l.id === language)?.locale ?? 'en-GB'

  const build = async () => {
    setBusy(true); setSince(Date.now()); setDocFilter('')
    try {
      setResult(await api.timeline(selectedIds, language || undefined))
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(false); setSince(null)
    }
  }

  const exportXlsx = async () => {
    if (!result) return
    try {
      const info = await api.timelineExport(`Timeline - ${result.documents.join(', ')}`.slice(0, 200), shown, selectedIds)
      await onExportCreated()
      notify(`Saved as ${info.filename} – see Exports`, 'info')
    } catch (e) { notify((e as RequestError).message) }
  }

  // At most 30 events: computed on every render, no memoization needed.
  const shown = (result?.events ?? []).filter((e) =>
    (!onlyVerified || e.status === 'verified') && (!docFilter || e.document_name === docFilter))
  const years: { year: string; events: TimelineEvent[] }[] = []
  for (const e of shown) {
    const year = e.status === 'invalid_date' ? 'Undated' : e.date.slice(0, 4)
    if (years.length && years[years.length - 1].year === year) years[years.length - 1].events.push(e)
    else years.push({ year, events: [e] })
  }
  const docNames = [...new Set((result?.events ?? []).map((e) => e.document_name).filter(Boolean))] as string[]

  return (
    <section className="card timeline-panel">
      <header className="panel-header">
        <h2>Timeline</h2>
        <span className="muted small">dated events from the selected documents · every date checked in its source</span>
      </header>

      <div className="row wrap">
        <span className="small muted grow">
          {selectedDocs.length ? `${selectedDocs.length} document${selectedDocs.length === 1 ? '' : 's'}: ${selectedDocs.map((d) => d.display_name).join(', ')}` : 'Select documents on the left.'}
        </span>
        <select value={language} onChange={(e) => setLanguage(e.target.value)} disabled={busy} title="Language of the event titles">
          {LANGUAGES.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
        </select>
        <button className="btn primary" onClick={build} disabled={!ready || busy || !selectedIds.length}>
          {busy ? 'Building…' : result ? 'Rebuild timeline' : 'Build timeline'}
        </button>
      </div>
      {!ready && <div className="notice warn small">Start a model in the Model launcher to build a timeline.</div>}
      {busy && since && <Progress phase="Building the timeline" hint="the model lists the dated events, then the app checks each date in its source" since={since} />}

      {!result && !busy && (
        <div className="empty-state">
          <h3>See everything that happened - and is planned - in date order</h3>
          <p className="small">The model reads the selected documents and lists their dated events: meetings, deadlines, decisions,
            incidents, launches. The app then checks that each date really appears in the passage the event cites, sorts the
            events and marks anything it could not verify.</p>
        </div>
      )}

      {result && (
        <>
          <div className="row wrap small">
            <span className="badge good">{result.counts.verified ?? 0} of {result.counts.total} dates verified</span>
            {result.counts.total - (result.counts.verified ?? 0) > 0 && (
              <span className="badge warn">{result.counts.total - (result.counts.verified ?? 0)} to review</span>
            )}
            {docNames.length > 1 && (
              <select value={docFilter} onChange={(e) => setDocFilter(e.target.value)}>
                <option value="">All documents</option>
                {docNames.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            )}
            <label className="check"><input type="checkbox" checked={onlyVerified} onChange={(e) => setOnlyVerified(e.target.checked)} /> only verified</label>
            <span className="grow" />
            <button className="btn small" onClick={exportXlsx} disabled={!shown.length}>Export to Excel</button>
          </div>

          {shown.length === 0 && <p className="small muted">No events match the filter.</p>}
          <div className="timeline">
            {years.map((g) => (
              <div key={g.year} className="timeline-year">
                <div className="timeline-year-label">{g.year}</div>
                {g.events.map((e, i) => {
                  const st = STATUS[e.status]
                  return (
                    <div key={`${e.date}-${i}`} className={`timeline-event ${e.status === 'verified' ? '' : 'unverified'}`}>
                      <div className="timeline-date">{formatDate(e, locale)}</div>
                      <div className="timeline-dot" />
                      <div className="timeline-card">
                        <div className="row between">
                          <strong>{e.title}</strong>
                          <span className={`badge ${st.tone}`} title={st.hint}>{st.label}</span>
                        </div>
                        {e.detail && <div className="small">{e.detail}</div>}
                        <div className="tiny muted row wrap">
                          {e.citation?.found
                            ? <button className="cite-chip" onClick={() => setOpenCitation(e.citation!)} title={`Open ${e.document_name} – ${e.citation.resolved_locator}`}>
                                {e.document_name} · {e.citation.resolved_locator}
                              </button>
                            : <span>{e.source || 'no source given'}</span>}
                          {e.date_text && <span>written as “{e.date_text}”</span>}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </>
      )}
      {openCitation && <SourceViewer citation={openCitation} onClose={() => setOpenCitation(null)} />}
    </section>
  )
}
