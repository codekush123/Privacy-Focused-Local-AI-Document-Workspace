import { useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatTokens, RequestError, streamAgent } from '../services/api'
import { markCitations } from '../services/text'
import type { AgentEvent, AgentStep, Citation, DocumentSummary, VerificationResult } from '../types/api'
import { Progress } from './Progress'
import { SourceViewer } from './SourceViewer'

interface Props {
  documents: DocumentSummary[]
  selectedIds: string[]
  ready: boolean
  onExportCreated: () => Promise<void>
  onGoToTab: (tab: string) => void
  notify: (msg: string, kind?: 'error' | 'info') => void
}

const STEP_LABEL: Record<string, string> = {
  router: 'Router agent',
  tool: 'Tool',
  verifier: 'Verifier agent',
  refine: 'Refinement',
}

const INTENT_LABEL: Record<string, string> = {
  answer: 'Answer from documents',
  summarize: 'Summarise',
  generate_docx: 'Generate Word file',
  generate_xlsx: 'Generate Excel file',
  generate_pptx: 'Generate PowerPoint',
  data_query: 'Query the table',
  quiz: 'Interactive quiz',
  translate: 'Translate',
  privacy_scan: 'Privacy scan',
  describe_images: 'Look at figures',
}

const EXAMPLES = [
  'Summarise the selected material for a revision session',
  'Make a five-slide presentation from these documents',
  'Which three students have the highest exam score?',
  'Does this document contain personal data?',
]

/**
 * Agent tab: one request, routed automatically to the right tool, then
 * fact-checked by the verifier agent, with the whole decision trace visible.
 */
export function AgentPanel({ documents, selectedIds, ready, onExportCreated, onGoToTab, notify }: Props) {
  const [request, setRequest] = useState('')
  const [steps, setSteps] = useState<AgentStep[]>([])
  const [result, setResult] = useState<AgentEvent | null>(null)
  const [busy, setBusy] = useState(false)
  const [autoVerify, setAutoVerify] = useState(false)
  const [allowFiles, setAllowFiles] = useState(true)
  const [openCitation, setOpenCitation] = useState<Citation | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [runStart, setRunStart] = useState<number | null>(null)
  const selectedDocs = documents.filter((d) => selectedIds.includes(d.id))

  const run = async () => {
    const text = request.trim()
    if (!text || busy) return
    setBusy(true); setSteps([]); setResult(null); setRunStart(Date.now())
    abortRef.current = new AbortController()
    try {
      await streamAgent(text, selectedIds, { allow_files: allowFiles, auto_verify: autoVerify }, {
        onStep: (s) => setSteps((prev) => {
          const i = prev.findIndex((p) => p.step === s.step && p.status === 'running')
          if (i >= 0) { const next = [...prev]; next[i] = s; return next }
          return [...prev, s]
        }),
        onResult: async (r) => { setResult(r); if (r.export) await onExportCreated() },
        onError: (msg) => notify(msg),
      }, abortRef.current.signal)
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(false); setRunStart(null); abortRef.current = null
    }
  }

  const answer = result?.answer ?? ''
  const citations = result?.citations
  const components = {
    a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
      if (href?.startsWith('cite:')) {
        const c = citations?.[Number(href.slice(5))]
        if (c) return <button className={`cite-chip ${c.found ? '' : 'missing'}`} onClick={() => setOpenCitation(c)}>{children}</button>
      }
      return <a href={href} target="_blank" rel="noreferrer">{children}</a>
    },
  }

  return (
    <section className="card agent">
      <header className="panel-header">
        <h2>Agent</h2>
        <span className="muted small">router → tool → verifier, all local</span>
      </header>

      <p className="small muted" style={{ margin: 0 }}>
        Describe what you want in plain language. A router agent picks the tool, the tool runs, and – if you tick
        “verify” – a second agent fact-checks the result against your documents.
        {selectedDocs.length > 0 && <> Using {selectedDocs.length} source{selectedDocs.length === 1 ? '' : 's'}.</>}
      </p>

      <div className="composer">
        <textarea rows={2} value={request} onChange={(e) => setRequest(e.target.value)} disabled={busy}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void run() } }}
          placeholder="e.g. “make a five-slide summary deck”, “what is the F1 formula?”, “average score per country”" />
        <div className="composer-row">
          <label className="check" title="Adds a second pass that checks every claim – slower, but shows how well grounded the answer is">
            <input type="checkbox" checked={autoVerify} onChange={(e) => setAutoVerify(e.target.checked)} />verify (slower)
          </label>
          <label className="check"><input type="checkbox" checked={allowFiles} onChange={(e) => setAllowFiles(e.target.checked)} />allow files</label>
          <span className="grow" />
          <button className="btn primary" onClick={run} disabled={busy || !ready || !request.trim()}>{busy ? 'Working…' : 'Run agent'}</button>
        </div>
        {!busy && steps.length === 0 && (
          <div className="quick-actions">
            {EXAMPLES.map((x, i) => <button key={i} className="btn chip" onClick={() => setRequest(x)}>{x}</button>)}
          </div>
        )}
      </div>

      {busy && runStart && <Progress phase="Agent working" hint="each step is one call to the local model" since={runStart} />}

      {steps.length > 0 && (
        <ol className="trace">
          {steps.map((s, i) => (
            <li key={i} className={`trace-step ${s.status}`}>
              <div className="row between">
                <strong>{STEP_LABEL[s.step] ?? s.step}</strong>
                <span className={`badge ${s.status === 'done' ? 'good' : s.status === 'error' ? 'bad' : 'plain'}`}>{s.status}</span>
              </div>
              {s.message && <div className="small muted">{s.message}</div>}
              {s.intent && (
                <div className="small">
                  Chose <strong>{INTENT_LABEL[s.intent] ?? s.intent}</strong>
                  {s.confidence && <> · <span className={`verdict ${s.confidence === 'high' ? 'supported' : s.confidence === 'medium' ? 'partially_supported' : 'unsupported'}`}>{s.confidence} confidence</span></>}
                  {s.reasoning && <div className="muted">{s.reasoning}</div>}
                  {s.task && <div className="muted">Task: “{s.task}”</div>}
                </div>
              )}
              {typeof s.grounding_score === 'number' && (
                <div className="small">
                  Grounding <strong>{s.grounding_score}%</strong>
                  {s.counts && <> · {s.counts.supported} supported, {s.counts.partially_supported} partly, {s.counts.unsupported} not in sources, {s.counts.contradicted} contradicted</>}
                  {s.overall && <div className="muted">{s.overall}</div>}
                </div>
              )}
              {s.error && <div className="notice error small">{s.error}</div>}
            </li>
          ))}
        </ol>
      )}

      {result && (
        <div className="agent-result">
          {answer && (
            <div className="bubble">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{markCitations(answer, citations)}</ReactMarkdown>
            </div>
          )}
          {result.export && (
            <a className="btn primary download" href={result.export.download_url} download={result.export.filename}>Download {result.export.filename}</a>
          )}
          {result.query && (
            <div className="table-wrap">
              <table className="data">
                <thead><tr>{result.query.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                <tbody>
                  {result.query.rows.slice(0, 15).map((r, i) => (
                    <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === 'number' ? 'num' : ''}>{v == null ? '' : String(v)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {result.handoff && (
            <button className="btn" onClick={() => onGoToTab(result.handoff!.tab)}>Open {result.handoff.tab} tab</button>
          )}
          {result.verification && <VerificationSummary v={result.verification} />}
          <div className="muted small">
            {result.context && <>Context {formatTokens(result.context.prompt_tokens)} / {formatTokens(result.context.context_size)} tokens · </>}
            {result.citation_stats && <>{result.citation_stats.resolved}/{result.citation_stats.total} citations verified · </>}
            finished in {result.elapsed_seconds}s
          </div>
        </div>
      )}

      {openCitation && <SourceViewer citation={openCitation} onClose={() => setOpenCitation(null)} />}
    </section>
  )
}

function VerificationSummary({ v }: { v: VerificationResult }) {
  return (
    <details className="verification">
      <summary className="small">
        Verifier: grounding {v.grounding_score}% – {v.counts.supported} supported, {v.counts.unsupported} not in sources
      </summary>
      <table className="data">
        <thead><tr><th>Claim</th><th>Verdict</th><th>Evidence</th></tr></thead>
        <tbody>
          {v.claims.map((c, i) => (
            <tr key={i}>
              <td>{c.claim}</td>
              <td><span className={`verdict ${c.verdict}`}>{c.verdict.replace('_', ' ')}</span></td>
              <td className="small">{c.evidence} {c.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
