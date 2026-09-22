import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api, RequestError } from '../services/api'
import type { DocumentSummary, FigureRecord, VisionPayload, VisionStatus } from '../types/api'

interface Props {
  documents: DocumentSummary[]
  onDocumentsChanged: () => Promise<void>
  notify: (msg: string, kind?: 'error' | 'info') => void
}

const SUPPORTED = ['pdf', 'pptx', 'docx']
const TYPE_LABEL: Record<string, string> = {
  chart: 'Chart', diagram: 'Diagram', photo: 'Photo', screenshot: 'Screenshot',
  table: 'Table image', formula: 'Formula', logo: 'Logo', other: 'Figure',
}

/**
 * Figures: extract images and vector charts from documents and describe them
 * with a local vision-language model. Accepted descriptions are merged into the
 * document text, so every other feature can use the visual content.
 */
export function FiguresPanel({ documents, onDocumentsChanged, notify }: Props) {
  const candidates = documents.filter((d) => SUPPORTED.includes(d.source_type))
  const [chosenId, setDocId] = useState('')
  const docId = candidates.some((d) => d.id === chosenId) ? chosenId : (candidates[0]?.id ?? '')
  const [status, setStatus] = useState<VisionStatus | null>(null)
  const [payload, setPayload] = useState<VisionPayload | null>(null)
  const [busy, setBusy] = useState<'extract' | 'describe' | null>(null)
  const [renderAll, setRenderAll] = useState(false)
  const [open, setOpen] = useState<FigureRecord | null>(null)

  useEffect(() => { api.visionStatus().then(setStatus).catch(() => {}) }, [])
  useEffect(() => {
    if (!docId) { setPayload(null); return }
    api.figures(docId).then(setPayload).catch(() => setPayload(null))
  }, [docId])

  const extract = async () => {
    setBusy('extract')
    try {
      setPayload(await api.extractFigures(docId, renderAll))
    } catch (e) { notify((e as RequestError).message) } finally { setBusy(null) }
  }

  const describe = async (ids: string[] = [], redescribe = false) => {
    setBusy('describe')
    try {
      const p = await api.describeFigures(docId, ids, redescribe)
      setPayload(p)
      await onDocumentsChanged()
      const failed = p.failures?.length ?? 0
      notify(`Described ${p.described ?? 0} figure(s)${failed ? `, ${failed} failed` : ''}. The descriptions are now part of the document text.`, failed ? 'error' : 'info')
    } catch (e) { notify((e as RequestError).message) } finally { setBusy(null) }
  }

  const toggleAccepted = async (fig: FigureRecord) => {
    try {
      setPayload(await api.updateFigure(docId, fig.id, { accepted: !fig.accepted }))
      await onDocumentsChanged()
    } catch (e) { notify((e as RequestError).message) }
  }

  const undescribed = payload?.images.filter((i) => !i.described).length ?? 0

  return (
    <section className="panel figures">
      <header className="panel-header">
        <h2>Figures</h2>
        <span className="muted small">charts and images read by a local vision model</span>
      </header>

      {status && !status.supports_vision && (
        <div className="notice error small">
          The loaded model cannot see images. {status.hint} Then reload this page.
        </div>
      )}

      {candidates.length === 0 ? (
        <div className="muted">Import a PDF, PowerPoint or Word document to analyse its figures. Charts drawn as vectors are rendered page by page, so they can be read too.</div>
      ) : (
        <>
          <div className="row gap wrap">
            <label className="field"><span>Document</span>
              <select value={docId} onChange={(e) => { setDocId(e.target.value); setPayload(null) }}>
                {candidates.map((d) => <option key={d.id} value={d.id}>{d.display_name}</option>)}
              </select>
            </label>
            <button className="btn self-end" onClick={extract} disabled={!!busy}>{busy === 'extract' ? 'Extracting…' : 'Find figures'}</button>
            <label className="row gap-s small self-end" title="Charts on text-heavy pages are not detected automatically; this renders every page instead.">
              <input type="checkbox" checked={renderAll} onChange={(e) => setRenderAll(e.target.checked)} />every page
            </label>
            <button className="btn primary self-end" onClick={() => describe()} disabled={!!busy || !payload?.images.length || !status?.supports_vision || undescribed === 0}>
              {busy === 'describe' ? 'Looking at figures…' : `Describe ${undescribed || ''} figure(s)`}
            </button>
            {payload && payload.images.some((i) => i.described) && (
              <button className="btn small self-end" onClick={() => describe([], true)} disabled={!!busy}>Redo all</button>
            )}
          </div>

          {payload && (
            <div className="muted small">
              {payload.summary.total === 0
                ? 'No figures found yet - click “Find figures”.'
                : `${payload.summary.total} figure(s), ${payload.summary.described} described. Descriptions are merged into the document text and can be cited like any other section.`}
            </div>
          )}

          <div className="figure-grid">
            {payload?.images.map((fig) => (
              <figure key={fig.id} className={`figure-card ${fig.accepted ? '' : 'excluded'}`}>
                <button className="thumb" onClick={() => setOpen(fig)} title="Open larger">
                  <img src={fig.url} alt={fig.title || fig.locator} loading="lazy" />
                </button>
                <figcaption>
                  <div className="row between">
                    <span className="muted small">{fig.locator} · {fig.kind === 'page_render' ? 'rendered page' : 'embedded image'}</span>
                    {fig.described && <span className="tag">{TYPE_LABEL[fig.figure_type] ?? 'Figure'}</span>}
                  </div>
                  {fig.described ? (
                    <>
                      <strong>{fig.title}</strong>
                      <p className="small">{fig.description}</p>
                      {fig.data_points.length > 0 && (
                        <ul className="small">{fig.data_points.slice(0, 6).map((d, i) => <li key={i}>{d}</li>)}</ul>
                      )}
                      <label className="row gap-s small">
                        <input type="checkbox" checked={fig.accepted} onChange={() => toggleAccepted(fig)} />
                        include this description in the document
                      </label>
                    </>
                  ) : (
                    <span className="muted small">Not described yet</span>
                  )}
                  <div className="row gap-s">
                    <button className="btn link small" onClick={() => describe([fig.id], true)} disabled={!!busy || !status?.supports_vision}>
                      {fig.described ? 're-describe' : 'describe'}
                    </button>
                    <button className="btn link small" onClick={() => setOpen(fig)}>ask about this figure</button>
                  </div>
                </figcaption>
              </figure>
            ))}
          </div>
        </>
      )}

      {open && <FigureDialog docId={docId} fig={open} onClose={() => setOpen(null)} notify={notify} canAsk={!!status?.supports_vision} />}
    </section>
  )
}

function FigureDialog({ docId, fig, onClose, notify, canAsk }: {
  docId: string; fig: FigureRecord; onClose: () => void; notify: (m: string, k?: 'error' | 'info') => void; canAsk: boolean
}) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)

  const ask = async () => {
    if (!question.trim()) return
    setBusy(true); setAnswer('')
    try {
      setAnswer((await api.askFigure(docId, fig.id, question)).answer)
    } catch (e) { notify((e as RequestError).message) } finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <header className="row between">
          <strong>{fig.title || 'Figure'} <span className="muted small">· {fig.locator}</span></strong>
          <button className="btn small" onClick={onClose}>Close</button>
        </header>
        <img className="figure-large" src={fig.url} alt={fig.title || fig.locator} />
        {fig.description && <p className="small">{fig.description}</p>}
        <div className="row gap">
          <input className="grow" value={question} onChange={(e) => setQuestion(e.target.value)} disabled={busy || !canAsk}
            placeholder={canAsk ? 'Ask about this figure, e.g. "which bar is highest?"' : 'Vision model not loaded'}
            onKeyDown={(e) => e.key === 'Enter' && ask()} />
          <button className="btn primary" onClick={ask} disabled={busy || !canAsk || !question.trim()}>{busy ? 'Looking…' : 'Ask'}</button>
        </div>
        {answer && <div className="msg-body"><ReactMarkdown>{answer}</ReactMarkdown></div>}
      </div>
    </div>
  )
}
