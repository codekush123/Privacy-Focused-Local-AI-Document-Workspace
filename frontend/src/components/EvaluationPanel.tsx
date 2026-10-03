import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, RequestError, streamEval } from '../services/api'
import type { EvalCase, EvalMetrics, EvalRunSummary, EvalSuite, RetrievalCheck } from '../types/api'
import { Progress } from './Progress'

interface Props {
  ready: boolean
  notify: (msg: string, kind?: 'error' | 'info') => void
}

const METRICS: { key: keyof EvalMetrics; label: string; hint: string; lowerIsBetter?: boolean }[] = [
  { key: 'overall', label: 'Overall', hint: 'details and "not in documents" count right/wrong, a list counts its recall' },
  { key: 'detail_accuracy', label: 'Small details', hint: 'exact number, date, name or code found' },
  { key: 'list_recall', label: 'Similar items: recall', hint: 'share of the expected items the answer lists' },
  { key: 'list_precision', label: 'Similar items: precision', hint: 'share of listed items that are correct' },
  { key: 'abstention_accuracy', label: "Says 'not in documents'", hint: 'unanswerable questions answered honestly' },
  { key: 'false_abstention_rate', label: "Wrongly says 'not found'", hint: 'answerable, but the model said it is not there', lowerIsBetter: true },
  { key: 'unsupported_number_rate', label: 'Invented numbers', hint: 'answers containing a number that is in no document', lowerIsBetter: true },
  { key: 'citation_accuracy', label: 'Cites the right place', hint: 'a citation points to the section holding the answer' },
  { key: 'prompt_leak_rate', label: 'Copies prompt text', hint: 'system-prompt text leaked into the answer', lowerIsBetter: true },
]

const GROUPS: { key: string; label: string }[] = [
  { key: 'all', label: 'All cases' },
  { key: 'difficulty=standard', label: 'Standard questions' },
  { key: 'difficulty=hard', label: 'Hard questions (multi-step, arithmetic, traps)' },
  { key: 'full/en/same', label: 'Full context · EN → EN' },
  { key: 'full/fi/same', label: 'Full context · FI → FI' },
  { key: 'retrieval/en/same', label: 'Retrieval · EN → EN' },
  { key: 'retrieval/fi/same', label: 'Retrieval · FI → FI' },
  { key: 'en->fi', label: 'English question → Finnish documents' },
  { key: 'fi->en', label: 'Finnish question → English documents' },
]

const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v * 100)} %`)

/**
 * The accuracy benchmark: a bilingual (English / Finnish) corpus about a
 * fictional company, questions with known answers, and deterministic scoring.
 * Every number on this tab comes from the same code as the command line.
 */
export function EvaluationPanel({ ready, notify }: Props) {
  const [suite, setSuite] = useState<EvalSuite | null>(null)
  const [retrieval, setRetrieval] = useState<RetrievalCheck | null>(null)
  const [checking, setChecking] = useState(false)
  const [runs, setRuns] = useState<EvalRunSummary[]>([])
  const [compare, setCompare] = useState<Set<string>>(new Set())
  const [group, setGroup] = useState('all')

  const [languages, setLanguages] = useState<Set<string>>(new Set(['en', 'fi']))
  const [strategies, setStrategies] = useState<Set<string>>(new Set(['full', 'retrieval']))
  const [cross, setCross] = useState(true)
  const [quick, setQuick] = useState(true)
  const [running, setRunning] = useState(false)
  const [runStart, setRunStart] = useState<number | null>(null)
  const [progress, setProgress] = useState<{ n: number; total: number; model?: string } | null>(null)
  const [live, setLive] = useState<EvalCase[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const [detailId, setDetailId] = useState<string>('')
  const [detail, setDetail] = useState<EvalCase[]>([])
  const [onlyWrong, setOnlyWrong] = useState(true)

  const refreshRuns = useCallback(async () => {
    try {
      const r = await api.evalResults()
      setRuns(r)
      setCompare((c) => (c.size ? c : new Set(r.filter((x) => x.finished_at).slice(0, 3).map((x) => x.id))))
    } catch { /* backend offline */ }
  }, [])

  useEffect(() => {
    api.evalSuite().then(setSuite).catch((e) => notify((e as RequestError).message))
    api.evalLastRetrieval().then(setRetrieval).catch(() => { })
    void refreshRuns()
  }, [notify, refreshRuns])

  useEffect(() => {
    if (!detailId) { setDetail([]); return }
    api.evalResult(detailId).then((r) => setDetail(r.cases)).catch((e) => notify((e as RequestError).message))
  }, [detailId, notify])

  const toggle = (set: Set<string>, value: string, apply: (s: Set<string>) => void) => {
    const next = new Set(set)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    if (next.size) apply(next)
  }

  const estimatedCases = useMemo(() => {
    if (!suite) return 0
    const perCat = quick ? 2 : Infinity
    const counts: Record<string, number> = {}
    let same = 0
    let crossN = 0
    for (const q of suite.questions) {
      counts[q.category] = (counts[q.category] ?? 0) + 1
      if (counts[q.category] > perCat) continue
      same += 1
      if (q.cross) crossN += 1
    }
    return languages.size * strategies.size * (same + (cross ? crossN : 0))
  }, [suite, quick, languages, strategies, cross])

  const runRetrieval = async () => {
    setChecking(true)
    try { setRetrieval(await api.evalRetrieval()) } catch (e) { notify((e as RequestError).message) } finally { setChecking(false) }
  }

  const start = async () => {
    setRunning(true); setRunStart(Date.now()); setLive([]); setProgress(null)
    abortRef.current = new AbortController()
    try {
      await streamEval({
        languages: [...languages], strategies: [...strategies], cross_lingual: cross, limit: quick ? 2 : null,
      }, {
        onEvent: (event, data) => {
          if (event === 'start') setProgress({ n: 0, total: data.total as number, model: data.model as string })
          else if (event === 'case') {
            setProgress((p) => ({ ...(p ?? { total: data.total as number }), n: data.n as number, total: data.total as number }))
            setLive((l) => [data.case as EvalCase, ...l].slice(0, 12))
          } else if (event === 'done') notify('Benchmark finished. The result is listed below.', 'info')
          else if (event === 'stopped') notify(String(data.message), 'info')
          else if (event === 'error') notify(String(data.error))
        },
      }, abortRef.current.signal)
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setRunning(false); setRunStart(null); abortRef.current = null
      await refreshRuns()
    }
  }

  const stop = async () => { try { await api.evalStop() } catch { /* ignore */ } }

  const removeRun = async (id: string) => {
    if (!confirm('Delete this benchmark result?')) return
    try {
      await api.evalDelete(id)
      setCompare((c) => { const n = new Set(c); n.delete(id); return n })
      if (detailId === id) setDetailId('')
      await refreshRuns()
    } catch (e) { notify((e as RequestError).message) }
  }

  const compared = runs.filter((r) => compare.has(r.id))

  return (
    <section className="card eval">
      <header className="panel-header">
        <h2>Evaluation</h2>
        <span className="muted small">accuracy benchmark · English and Finnish · scored without a second model</span>
      </header>

      {suite && (
        <div className="eval-intro small">
          <p className="muted">
            <strong>{suite.questions.length} questions</strong> about a fictional energy company, asked over the same
            four documents (PDF, Word, PowerPoint, Excel) in English and in Finnish:
            {' '}{suite.by_category.detail ?? 0} small details, {suite.by_category.list ?? 0} "find all similar items"
            questions and {suite.by_category.unanswerable ?? 0} questions the documents cannot answer.
            {' '}{suite.by_difficulty?.hard ?? 0} of them are hard: they combine several facts, need arithmetic or
            negation, or set a near-miss trap. {suite.cross_lingual} are also asked across languages. Because the company is invented, a model can
            only answer correctly from the documents.
          </p>
          {suite.problems.length > 0
            ? <div className="notice error">Suite self-check failed: {suite.problems.slice(0, 3).join('; ')}</div>
            : <span className="badge good">suite self-check passed</span>}
        </div>
      )}

      {/* ------------------------------------------------ retrieval check */}
      <div className="eval-block">
        <div className="row between">
          <h3>1 · Retrieval check <span className="muted small">no model, a few seconds</span></h3>
          <button className="btn small" onClick={runRetrieval} disabled={checking}>{checking ? 'Checking…' : 'Run retrieval check'}</button>
        </div>
        <p className="small muted">Does the search step put the passage that holds the answer in front of the model? Plain BM25
          against the language-aware version (Finnish stemming, word prefixes, indexed slide titles and headings).</p>
        {retrieval && (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Retrieval</th><th>Question → documents</th><th>Recall@1</th><th>Recall@3</th><th>Recall@5</th><th title="share of evidence that ended up in the prompt">Reached the model</th><th>Corpus sent</th></tr></thead>
              <tbody>
                {retrieval.rows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.stemming ? 'language-aware' : 'plain BM25'}</td>
                    <td>{r.question_language.toUpperCase()} → {r.corpus.toUpperCase()}</td>
                    <td className="num">{pct(r['recall@1'])}</td>
                    <td className="num">{pct(r['recall@3'])}</td>
                    <td className="num">{pct(r['recall@5'])}</td>
                    <td className="num"><Bar value={r.context_recall} /></td>
                    <td className="num">{pct(r.share_of_corpus_sent)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------- run */}
      <div className="eval-block">
        <h3>2 · Ask the loaded model</h3>
        <p className="small muted">Every question goes through the real pipeline (context strategy → llama-server → citations).
          The benchmark uses whichever model is loaded; load each model in turn to compare them.</p>
        <div className="row wrap small">
          <span className="muted">Documents:</span>
          {[['en', 'English'], ['fi', 'Finnish']].map(([id, label]) => (
            <label key={id} className="check"><input type="checkbox" checked={languages.has(id)} disabled={running}
              onChange={() => toggle(languages, id, setLanguages)} /> {label}</label>
          ))}
          <span className="muted">· Context:</span>
          {[['full', 'Full'], ['retrieval', 'Retrieval']].map(([id, label]) => (
            <label key={id} className="check"><input type="checkbox" checked={strategies.has(id)} disabled={running}
              onChange={() => toggle(strategies, id, setStrategies)} /> {label}</label>
          ))}
          <label className="check"><input type="checkbox" checked={cross} disabled={running} onChange={(e) => setCross(e.target.checked)} /> cross-lingual</label>
          <label className="check"><input type="checkbox" checked={quick} disabled={running} onChange={(e) => setQuick(e.target.checked)} /> quick (2 per category)</label>
          <span className="grow" />
          <span className="muted">{estimatedCases} questions</span>
          {running
            ? <button className="btn" onClick={stop}>Stop</button>
            : <button className="btn primary" onClick={start} disabled={!ready || !suite}>Run benchmark</button>}
        </div>
        {!ready && <div className="notice warn small">Start a model in the Model launcher to run the benchmark.</div>}
        {running && runStart && (
          <>
            <Progress phase={progress ? `Question ${progress.n} of ${progress.total}` : 'Starting'} hint={progress?.model ?? ''} since={runStart} />
            {progress && <div className="meter"><span style={{ width: `${(100 * progress.n) / Math.max(1, progress.total)}%` }} /></div>}
          </>
        )}
        {live.length > 0 && (
          <ul className="eval-live small">
            {live.map((c, i) => <li key={i}><Verdict c={c} /> <span className="mono">{c.id}</span> {c.strategy} · {c.question_language}→{c.corpus_language} · {c.seconds}s</li>)}
          </ul>
        )}
      </div>

      {/* --------------------------------------------------- results */}
      <div className="eval-block">
        <div className="row between">
          <h3>3 · Results</h3>
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            {GROUPS.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
          </select>
        </div>
        {runs.length === 0 && <p className="small muted">No benchmark runs yet.</p>}
        {runs.length > 0 && (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th></th><th>Model</th><th>Started</th><th>Questions</th><th>Overall</th><th></th></tr></thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td><input type="checkbox" checked={compare.has(r.id)} onChange={() => setCompare((c) => { const n = new Set(c); if (n.has(r.id)) n.delete(r.id); else n.add(r.id); return n })} title="compare" /></td>
                    <td className="truncate" style={{ maxWidth: 260 }} title={r.model ?? ''}>{shortModel(r.model)}</td>
                    <td className="small">{r.started_at ? new Date(r.started_at).toLocaleString() : ''}</td>
                    <td className="num">{r.completed_cases}/{r.total_cases}{!r.finished_at && ' (incomplete)'}</td>
                    <td className="num">{pct(r.summary?.overall)}</td>
                    <td className="row tight">
                      <button className="btn link small" onClick={() => setDetailId(detailId === r.id ? '' : r.id)}>{detailId === r.id ? 'hide answers' : 'answers'}</button>
                      <button className="btn link small danger" onClick={() => removeRun(r.id)}>delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {compared.length > 0 && <Comparison runs={compared} group={group} />}
        {detailId && (
          <CaseTable cases={detail} onlyWrong={onlyWrong} setOnlyWrong={setOnlyWrong} />
        )}
      </div>
    </section>
  )
}

function shortModel(m: string | null | undefined) {
  return (m ?? 'unknown model').replace(/\.gguf$/i, '')
}

function Bar({ value, lowerIsBetter = false }: { value: number | null | undefined; lowerIsBetter?: boolean }) {
  if (value == null) return <span className="dim">–</span>
  const good = lowerIsBetter ? value <= 0.1 : value >= 0.8
  const bad = lowerIsBetter ? value >= 0.3 : value < 0.5
  return (
    <span className="eval-bar" title={pct(value)}>
      <span className={`fill ${good ? 'good' : bad ? 'bad' : 'mid'}`} style={{ width: `${Math.round(value * 100)}%` }} />
      <span className="val">{pct(value)}</span>
    </span>
  )
}

/** Runs side by side, one row per metric, for the chosen group of cases. */
function Comparison({ runs, group }: { runs: EvalRunSummary[]; group: string }) {
  const [full, setFull] = useState<Record<string, Record<string, EvalMetrics>>>({})
  useEffect(() => {
    let cancelled = false
    Promise.all(runs.map((r) => api.evalResult(r.id).then((d) => [r.id, d.summary] as const)))
      .then((pairs) => { if (!cancelled) setFull(Object.fromEntries(pairs)) })
      .catch(() => { })
    return () => { cancelled = true }
  }, [runs])
  const cols = runs.filter((r) => full[r.id]?.[group])
  if (!cols.length) return <p className="small muted">The selected runs have no cases in this group.</p>
  return (
    <div className="table-wrap">
      <table className="data eval-compare">
        <thead><tr><th>Metric</th>{cols.map((r) => <th key={r.id} title={r.id}>{shortModel(r.model)}</th>)}</tr></thead>
        <tbody>
          {METRICS.map((m) => (
            <tr key={m.key}>
              <td title={m.hint}>{m.label}{m.lowerIsBetter && <span className="dim tiny"> (lower is better)</span>}</td>
              {cols.map((r) => <td key={r.id}><Bar value={full[r.id][group][m.key] as number | null} lowerIsBetter={m.lowerIsBetter} /></td>)}
            </tr>
          ))}
          <tr><td>Seconds per question</td>{cols.map((r) => <td key={r.id} className="num">{full[r.id][group].seconds_mean ?? '–'}</td>)}</tr>
          <tr><td>Cases</td>{cols.map((r) => <td key={r.id} className="num">{full[r.id][group].cases}</td>)}</tr>
        </tbody>
      </table>
    </div>
  )
}

function Verdict({ c }: { c: EvalCase }) {
  if (c.error) return <span className="badge bad">error</span>
  if (c.correct) return <span className="badge good">right</span>
  if (c.category === 'list' && c.score > 0) return <span className="badge warn">{Math.round(c.score * 100)} %</span>
  return <span className="badge bad">wrong</span>
}

function CaseTable({ cases, onlyWrong, setOnlyWrong }: { cases: EvalCase[]; onlyWrong: boolean; setOnlyWrong: (v: boolean) => void }) {
  const shown = onlyWrong ? cases.filter((c) => !c.correct) : cases
  return (
    <div className="col">
      <label className="check small"><input type="checkbox" checked={onlyWrong} onChange={(e) => setOnlyWrong(e.target.checked)} /> only answers that were not fully right ({cases.filter((c) => !c.correct).length} of {cases.length})</label>
      <div className="table-wrap">
        <table className="data">
          <thead><tr><th>Result</th><th>Question</th><th>Answer</th><th>Notes</th></tr></thead>
          <tbody>
            {shown.map((c, i) => (
              <tr key={i}>
                <td><Verdict c={c} /><div className="tiny dim">{c.id} · {c.strategy} · {c.question_language}→{c.corpus_language}</div></td>
                <td className="small">{c.question}</td>
                <td className="small eval-answer">{c.error ?? c.answer}</td>
                <td className="tiny">
                  {c.missed_items?.length ? <div>missed: {c.missed_items.join(', ')}</div> : null}
                  {c.extra_items?.length ? <div>wrongly listed: {c.extra_items.join(', ')}</div> : null}
                  {c.unsupported_numbers?.length ? <div className="danger-text">numbers not in documents: {c.unsupported_numbers.join(', ')}</div> : null}
                  {c.prompt_leak && <div className="danger-text">copied prompt text</div>}
                  {c.category !== 'unanswerable' && <div className="dim">citation {c.citation_hit ? 'points to the answer' : c.citations ? 'elsewhere' : 'missing'}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
