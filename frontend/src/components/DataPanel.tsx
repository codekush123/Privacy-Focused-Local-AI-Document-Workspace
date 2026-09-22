import { useEffect, useState } from 'react'
import { api, RequestError } from '../services/api'
import { Progress } from './Progress'
import type { DataInfo, DocumentSummary, QueryResult } from '../types/api'

interface Props {
  documents: DocumentSummary[]
  ready: boolean
  onExportCreated: () => Promise<void>
  notify: (msg: string, kind?: 'error' | 'info') => void
}

const EXAMPLES = [
  'Which 3 rows have the highest value in the last numeric column?',
  'Average of each numeric column per category',
  'Show rows where the value is below 60, sorted ascending',
]

/**
 * Ask your data: the model writes a query plan (filters / group-by / sort / chart),
 * the backend executes it on the real table, so every number is exact.
 */
export function DataPanel({ documents, ready, onExportCreated, notify }: Props) {
  const tables = documents.filter((d) => d.source_type === 'csv' || d.source_type === 'xlsx')
  const [chosenId, setDocId] = useState<string>('')
  const docId = tables.some((d) => d.id === chosenId) ? chosenId : (tables[0]?.id ?? '')
  const [sheet, setSheet] = useState<string>('')
  const [info, setInfo] = useState<DataInfo | null>(null)
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<QueryResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState<{ q: string; r: QueryResult }[]>([])
  const [runStart, setRunStart] = useState<number | null>(null)

  useEffect(() => {
    if (!docId) { setInfo(null); return }
    api.dataInfo(docId, sheet || undefined).then(setInfo).catch((e) => { setInfo(null); notify((e as RequestError).message) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, sheet])

  const ask = async (q?: string) => {
    const text = (q ?? question).trim()
    if (!text || !docId) return
    setBusy(true); setRunStart(Date.now())
    try {
      const r = await api.dataQuery(docId, text, sheet || undefined)
      setResult(r)
      setHistory((h) => [{ q: text, r }, ...h].slice(0, 10))
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(false); setRunStart(null)
    }
  }

  const exportXlsx = async () => {
    if (!result) return
    try {
      const i = await api.dataExport(question || 'Query result', result.columns, result.rows, docId, result.plan.explanation)
      await onExportCreated()
      notify(`Saved as ${i.filename} – see Exports`, 'info')
    } catch (e) { notify((e as RequestError).message) }
  }

  return (
    <section className="card data">
      <header className="panel-header">
        <h2>Ask your data</h2>
        <span className="muted small">natural language → query plan → exact local execution</span>
      </header>

      {tables.length === 0 ? (
        <div className="muted">Import a CSV or Excel file to ask questions about its rows. The model never does the arithmetic itself: it writes a query plan that the app executes on the real table.</div>
      ) : (
        <>
          <div className="row wrap">
            <label className="field"><span>Table</span>
              <select value={docId} onChange={(e) => { setDocId(e.target.value); setSheet(''); setResult(null) }}>
                {tables.map((t) => <option key={t.id} value={t.id}>{t.display_name}</option>)}
              </select>
            </label>
            {info && info.sheets.length > 1 && (
              <label className="field"><span>Sheet</span>
                <select value={sheet} onChange={(e) => setSheet(e.target.value)}>
                  {info.sheets.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
            )}
            {info && <div className="muted small self-end">{info.row_count} rows · {info.columns.length} columns: {info.columns.join(', ')}</div>}
          </div>

          <div className="composer">
            <textarea rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} disabled={busy}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void ask() } }}
              placeholder='e.g. "Average exam score per country as a bar chart" or "Top 5 students by weighted score (25% a1, 25% a2, 50% exam)"' />
            <div className="composer-row">
              <span className="muted small grow">Examples: {EXAMPLES.map((x, i) => <button key={i} className="btn link small" onClick={() => setQuestion(x)}>{x}</button>)}</span>
              <button className="btn primary" onClick={() => ask()} disabled={!ready || busy || !question.trim()}>{busy ? 'Planning…' : 'Ask'}</button>
            </div>
          </div>

          {busy && runStart && <Progress phase="Planning the query" hint="the model writes a plan, the app runs it on the real table" since={runStart} />}

          {result && (
            <div className="col">
              <div className="plan">
                <strong>Plan:</strong> {result.plan.explanation}
                <details className="small muted"><summary>show query plan (what the app executed)</summary><pre>{JSON.stringify(result.plan, null, 1)}</pre></details>
              </div>
              {result.plan.chart.type !== 'none' && <SimpleChart result={result} />}
              <div className="table-wrap">
                <table className="data">
                  <thead><tr>{result.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>
                    {result.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === 'number' ? 'num' : ''}>{v == null ? '' : String(v)}</td>)}</tr>)}
                  </tbody>
                </table>
              </div>
              <div className="row between small muted">
                <span>{result.row_count} of {result.total_rows} result rows shown</span>
                <button className="btn small" onClick={exportXlsx}>Export to Excel</button>
              </div>
            </div>
          )}

          {history.length > 1 && (
            <details className="small muted"><summary>previous questions</summary>
              <ul>{history.slice(1).map((h, i) => <li key={i}><button className="btn link small" onClick={() => { setQuestion(h.q); setResult(h.r) }}>{h.q}</button></li>)}</ul>
            </details>
          )}
        </>
      )}
    </section>
  )
}

/** Minimal single-series bar / line chart (one hue, thin marks, hover tooltips, table always present). */
function SimpleChart({ result }: { result: QueryResult }) {
  const { x, y, type } = result.plan.chart
  const xi = result.columns.indexOf(x)
  const yi = result.columns.indexOf(y)
  if (xi < 0 || yi < 0) return null
  const points = result.rows.map((r) => ({ label: String(r[xi] ?? ''), value: typeof r[yi] === 'number' ? (r[yi] as number) : Number(r[yi]) })).filter((p) => !Number.isNaN(p.value)).slice(0, 40)
  if (!points.length) return null
  const W = 640, H = 220, padL = 48, padB = 44, padT = 12, padR = 12
  const max = Math.max(...points.map((p) => p.value), 0)
  const min = Math.min(...points.map((p) => p.value), 0)
  const span = max - min || 1
  const plotW = W - padL - padR, plotH = H - padT - padB
  const sx = (i: number) => padL + (i + 0.5) * (plotW / points.length)
  const sy = (v: number) => padT + plotH - ((v - min) / span) * plotH
  const bw = Math.max(4, Math.min(28, (plotW / points.length) * 0.6))
  const ticks = [min, min + span / 2, max]
  return (
    <figure className="chart">
      <figcaption className="small muted">{y} by {x}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${type} chart of ${y} by ${x}`}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={sy(t)} y2={sy(t)} className="grid" />
            <text x={padL - 6} y={sy(t) + 4} className="tick" textAnchor="end">{Number.isInteger(t) ? t : t.toFixed(1)}</text>
          </g>
        ))}
        <line x1={padL} x2={W - padR} y1={sy(0)} y2={sy(0)} className="axis" />
        {type === 'bar' && points.map((p, i) => (
          <g key={i}>
            <rect x={sx(i) - bw / 2} y={Math.min(sy(p.value), sy(0))} width={bw} height={Math.max(2, Math.abs(sy(0) - sy(p.value)))} rx={4} className="mark">
              <title>{p.label}: {p.value}</title>
            </rect>
          </g>
        ))}
        {type === 'line' && (
          <>
            <polyline points={points.map((p, i) => `${sx(i)},${sy(p.value)}`).join(' ')} className="line" />
            {points.map((p, i) => <circle key={i} cx={sx(i)} cy={sy(p.value)} r={4} className="mark"><title>{p.label}: {p.value}</title></circle>)}
          </>
        )}
        {points.map((p, i) => (
          <text key={i} x={sx(i)} y={H - padB + 14} className="tick" textAnchor={points.length > 8 ? 'end' : 'middle'}
            transform={points.length > 8 ? `rotate(-35 ${sx(i)} ${H - padB + 14})` : undefined}>
            {p.label.length > 14 ? p.label.slice(0, 13) + '…' : p.label}
          </text>
        ))}
      </svg>
    </figure>
  )
}
