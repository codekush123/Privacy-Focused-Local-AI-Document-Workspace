import { useEffect, useRef, useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, formatTokens, RequestError, streamChat } from '../services/api'
import type {
  ChatMessage, Citation, ContextCheck, DocumentSummary, ExportInfo, StrategyName, StrategyOption,
  TextExportKind, VerificationResult, Verdict,
} from '../types/api'
import { markCitations, splitThinking } from '../services/text'
import { Progress, streamPhase } from './Progress'
import { SourceViewer } from './SourceViewer'

type OutputMode = 'chat' | 'docx' | 'xlsx' | 'pptx' | 'csv'

const MODE_LABEL: Record<OutputMode, string> = {
  chat: 'Answer in chat',
  docx: 'Generate Word (.docx)',
  xlsx: 'Generate Excel (.xlsx)',
  pptx: 'Generate PowerPoint (.pptx)',
  csv: 'Generate CSV',
}

const SAVE_KINDS: { kind: TextExportKind; label: string }[] = [
  { kind: 'docx', label: 'Word (.docx)' },
  { kind: 'pdf', label: 'PDF' },
  { kind: 'tex', label: 'LaTeX (.tex)' },
  { kind: 'md', label: 'Markdown (.md)' },
  { kind: 'txt', label: 'Text (.txt)' },
]

const QUICK_LABELS: Record<string, string> = {
  summarize: 'Summarize',
  quiz: 'Generate quiz',
  study_notes: 'Create study notes',
  compare: 'Compare documents',
  action_items: 'Action items',
  explain_simply: 'Explain simply',
}

const LANGUAGES = ['English', 'Finnish', 'Swedish', 'German', 'French', 'Spanish', 'Chinese', 'Arabic', 'Russian', 'Hindi']

interface Props {
  documents: DocumentSummary[]
  selectedIds: string[]
  aiAllowed: boolean
  connected: boolean
  onContext: (ctx: ContextCheck | null) => void
  onExportCreated: () => Promise<void>
  notify: (msg: string, kind?: 'error' | 'info') => void
}

let counter = 0
const nextId = () => `m${Date.now()}_${counter++}`

export function ChatPanel({ documents, selectedIds, aiAllowed, connected, onContext, onExportCreated, notify }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [prompt, setPrompt] = useState('')
  const [mode, setMode] = useState<OutputMode>('chat')
  const [busy, setBusy] = useState(false)
  const [quick, setQuick] = useState<Record<string, string>>({})
  const [precheck, setPrecheck] = useState<ContextCheck | null>(null)
  const [language, setLanguage] = useState('Finnish')
  const [openCitation, setOpenCitation] = useState<Citation | null>(null)
  const [runStart, setRunStart] = useState<number | null>(null)
  const [strategy, setStrategy] = useState<StrategyName | ''>('')
  const [strategies, setStrategies] = useState<StrategyOption[]>([])
  const [firstToken, setFirstToken] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const selectedDocs = documents.filter((d) => selectedIds.includes(d.id))

  useEffect(() => { api.quickActions().then(setQuick).catch(() => {}) }, [])
  useEffect(() => { api.strategies().then((s) => setStrategies(s.strategies)).catch(() => {}) }, [])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  // Pre-check the context whenever the selection changes so the usage bar is always current.
  useEffect(() => {
    if (!connected || !aiAllowed) { setPrecheck(null); onContext(null); return }
    let cancelled = false
    api.contextCheck(prompt || '(question)', selectedIds, strategy || undefined)
      .then((c) => { if (!cancelled) { setPrecheck(c); onContext(c) } })
      .catch(() => { if (!cancelled) { setPrecheck(null) } })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds.join(','), connected, aiAllowed, strategy])

  const update = (id: string, patch: Partial<ChatMessage>) =>
    setMessages((ms) => ms.map((m) => (m.id === id ? { ...m, ...patch } : m)))

  const send = async () => {
    const text = prompt.trim()
    if (!text || busy) return
    setPrompt('')
    const userMsg: ChatMessage = { id: nextId(), role: 'user', content: text, sources: selectedDocs.map((d) => d.display_name) }
    const asstId = nextId()
    setMessages((ms) => [...ms, userMsg, { id: asstId, role: 'assistant', content: '', streaming: true }])
    setBusy(true)
    setRunStart(Date.now())
    setFirstToken(false)
    const history = messages.filter((m) => !m.error && m.content).slice(-8).map((m) => ({ role: m.role, content: splitThinking(m.content).answer || m.content }))

    try {
      if (mode === 'chat') {
        abortRef.current = new AbortController()
        await streamChat(text, selectedIds, history, {
          onContext: (ctx) => {
            update(asstId, { context: ctx, sources: ctx.sources, sourceMap: ctx.source_map, strategyInfo: ctx.strategy_info })
            onContext(ctx)
          },
          onDelta: (d) => {
            setFirstToken(true)
            setMessages((ms) => ms.map((m) => (m.id === asstId ? { ...m, content: m.content + d } : m)))
          },
          onDone: (done) => update(asstId, { streaming: false, citations: done.citations, citationStats: done.citation_stats }),
          onError: (err) => update(asstId, { streaming: false, error: err }),
        }, abortRef.current.signal, strategy || undefined)
        update(asstId, { streaming: false })
      } else {
        update(asstId, { content: `Generating ${MODE_LABEL[mode].replace('Generate ', '')} from ${selectedDocs.length} document(s)… (structured JSON → local file)` })
        const info: ExportInfo = await api.generate(mode, text, selectedIds)
        update(asstId, { streaming: false, content: `**${info.filename}** is ready (${(info.size_bytes / 1024).toFixed(1)} KB).`, exportInfo: info })
        await onExportCreated()
      }
    } catch (e) {
      const err = e as RequestError
      const extra = err.suggestions?.length ? '\n\nSuggestions:\n' + err.suggestions.map((s) => `- ${s}`).join('\n') : ''
      update(asstId, { streaming: false, content: '', error: err.message + extra })
      if (err.context) onContext(err.context)
    } finally {
      setBusy(false)
      setRunStart(null)
      abortRef.current = null
    }
  }

  const stop = () => abortRef.current?.abort()

  const verifyMessage = async (m: ChatMessage) => {
    if (!selectedIds.length) { notify('Select the documents the answer was based on first.'); return }
    update(m.id, { verifying: true })
    try {
      const v = await api.verify(splitThinking(m.content).answer, selectedIds)
      update(m.id, { verification: v, verifying: false })
    } catch (e) {
      update(m.id, { verifying: false })
      notify((e as RequestError).message)
    }
  }

  const insertTranslate = async () => {
    try {
      setPrompt((await api.translatePrompt(language)).prompt)
    } catch (e) { notify((e as RequestError).message) }
  }

  const saveAnswer = async (m: ChatMessage, kind: TextExportKind) => {
    try {
      const q = messages[messages.findIndex((x) => x.id === m.id) - 1]?.content ?? ''
      const title = q.length > 80 ? q.slice(0, 77) + '…' : q
      const info = await api.saveText(splitThinking(m.content).answer, kind, q, selectedIds, title)
      await onExportCreated()
      notify(`Saved as ${info.filename} – see Exports`, 'info')
    } catch (e) { notify((e as RequestError).message, 'error') }
  }

  const disabled = !connected || !aiAllowed
  const over = precheck ? !precheck.fits : false

  return (
    <section className="card chat">
      <header className="panel-header">
        <h2>Chat</h2>
        <span className="dim tiny truncate" style={{ maxWidth: '55%' }}>
          {selectedDocs.length === 0 ? 'no documents selected' : selectedDocs.map((d) => d.display_name).join(', ')}
        </span>
      </header>

      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <h3>Ask your documents</h3>
            <p className="small">Select sources on the left and ask a question. Answers cite their sources – click a citation to open the exact passage.</p>
            <p className="small">Switch the output mode below to get a Word, Excel or PowerPoint file instead of a chat answer.</p>
          </div>
        )}
        {messages.map((m) => (
          <MessageView key={m.id} m={m} onSave={saveAnswer} onVerify={verifyMessage} onOpenCitation={setOpenCitation} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="quick-actions">
        {Object.entries(quick).map(([k, v]) => (
          <button key={k} className="btn chip" onClick={() => setPrompt(v)} disabled={busy}>{QUICK_LABELS[k] ?? k}</button>
        ))}
        <span className="translate-ctl">
          <button className="btn chip" onClick={insertTranslate} disabled={busy}>Translate to</button>
          <input className="lang" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="language" list="languages" />
          <datalist id="languages">{LANGUAGES.map((l) => <option key={l} value={l} />)}</datalist>
        </span>
      </div>

      {busy && runStart && mode === 'chat' && <Progress {...streamPhase(firstToken)} since={runStart} />}
      {busy && runStart && mode !== 'chat' && (
        <Progress phase={`Generating ${MODE_LABEL[mode].replace('Generate ', '')}`} hint="structured output, then the file is written locally" since={runStart} />
      )}

      {disabled && (
        <div className="notice error small">
          {!aiAllowed ? 'AI requests are blocked: LOCAL ONLY mode requires a localhost llama-server endpoint.' : 'llama-server is not running. Use "Model launcher" on the right to enter the path to your llama-server and model, or start llama-server yourself.'}
        </div>
      )}
      {!disabled && over && precheck && (
        <div className="notice error small">
          {precheck.message}
          <ul>{precheck.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      )}

      <div className="composer">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
          placeholder={mode === 'chat' ? 'Ask a question about the selected documents… (Enter to send, Shift+Enter for newline)' : `Describe the ${MODE_LABEL[mode].replace('Generate ', '')} you want, e.g. "Create 10 quiz questions with answers"`}
          rows={3}
          disabled={busy}
        />
        <div className="composer-row">
          <select value={mode} onChange={(e) => setMode(e.target.value as OutputMode)} disabled={busy}>
            {(Object.keys(MODE_LABEL) as OutputMode[]).map((k) => <option key={k} value={k}>{MODE_LABEL[k]}</option>)}
          </select>
          {strategies.length > 0 && (
            <select value={strategy} onChange={(e) => setStrategy(e.target.value as StrategyName | '')} disabled={busy}
              title={strategies.find((s) => s.id === strategy)?.description ?? 'How the documents are turned into a prompt'}>
              <option value="">Context: default</option>
              {strategies.map((s) => <option key={s.id} value={s.id}>Context: {s.label}</option>)}
            </select>
          )}
          <span className="muted small grow">
            {precheck && !over && `Context: ${formatTokens(precheck.prompt_tokens)} / ${formatTokens(precheck.context_size)} tokens`}
          </span>
          {busy && mode === 'chat' && <button className="btn" onClick={stop}>Stop</button>}
          <button className="btn primary" onClick={send} disabled={busy || disabled || !prompt.trim() || over}>
            {busy ? (mode === 'chat' ? 'Answering…' : 'Generating…') : mode === 'chat' ? 'Send' : 'Generate'}
          </button>
        </div>
      </div>
      {openCitation && <SourceViewer citation={openCitation} onClose={() => setOpenCitation(null)} />}
    </section>
  )
}

const VERDICT_LABEL: Record<Verdict, string> = {
  supported: 'Supported',
  partially_supported: 'Partly supported',
  unsupported: 'Not in sources',
  contradicted: 'Contradicted',
}

function VerificationView({ v, onOpenCitation }: { v: VerificationResult; onOpenCitation: (c: Citation) => void }) {
  const cite = (source: string) => v.citations.find((c) => c.marker === source)
  const tone = v.grounding_score >= 80 ? 'green' : v.grounding_score >= 50 ? 'amber' : 'red'
  return (
    <div className="verification">
      <div className="row between">
        <strong>Fact-check against the selected sources</strong>
        <span className={`badge ${tone}`}>grounding {v.grounding_score}%</span>
      </div>
      <div className="small muted">{v.overall}</div>
      <table className="claims">
        <thead><tr><th>Claim</th><th>Verdict</th><th>Evidence</th></tr></thead>
        <tbody>
          {v.claims.map((c, i) => {
            const ci = cite(c.source)
            return (
              <tr key={i}>
                <td>{c.claim}</td>
                <td><span className={`verdict ${c.verdict}`}>{VERDICT_LABEL[c.verdict]}</span></td>
                <td>
                  {c.evidence && <em>“{c.evidence}”</em>}{' '}
                  {c.source && (ci
                    ? <button className={`cite-chip ${ci.found ? '' : 'missing'}`} onClick={() => onOpenCitation(ci)}>{c.source.slice(1, -1)}</button>
                    : <span className="muted small">{c.source}</span>)}
                  {c.note && <div className="muted small">{c.note}</div>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function MessageView({ m, onSave, onVerify, onOpenCitation }: {
  m: ChatMessage
  onSave: (m: ChatMessage, kind: TextExportKind) => void
  onVerify: (m: ChatMessage) => void
  onOpenCitation: (c: Citation) => void
}) {
  const [showThinking, setShowThinking] = useState(false)
  const { thinking, answer } = m.role === 'assistant' ? splitThinking(m.content) : { thinking: null, answer: m.content }
  const marked = m.streaming ? answer : markCitations(answer, m.citations)
  const components = {
    a: ({ href, children }: { href?: string; children?: ReactNode }) => {
      if (href?.startsWith('cite:')) {
        const c = m.citations?.[Number(href.slice(5))]
        if (c) {
          return (
            <button
              className={`cite-chip ${c.found ? '' : 'missing'}`}
              title={c.found ? `Open ${c.document_name} – ${c.resolved_locator}` : 'This citation could not be matched to a section'}
              onClick={() => onOpenCitation(c)}
            >
              {children}
            </button>
          )
        }
      }
      return <a href={href} target="_blank" rel="noreferrer">{children}</a>
    },
  }
  return (
    <div className={`msg ${m.role}`}>
      <div className="msg-role">{m.role === 'user' ? 'You' : 'Local model'}</div>
      {m.role === 'user' ? (
        <div className="bubble"><pre className="user-text">{m.content}</pre></div>
      ) : (
        <div className="bubble">
          {thinking != null && (
            <details className="thinking" open={showThinking} onToggle={(e) => setShowThinking((e.target as HTMLDetailsElement).open)}>
              <summary className="muted small">Model reasoning {m.streaming && !answer ? '(thinking…)' : ''}</summary>
              <pre className="small muted">{thinking}</pre>
            </details>
          )}
          {answer && <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{marked}</ReactMarkdown>}
          
          {m.streaming && m.content && <span className="cursor">▍</span>}
          {m.error && <div className="notice error small"><ReactMarkdown>{m.error}</ReactMarkdown></div>}
          {m.exportInfo && (
            <a className="btn primary download" href={m.exportInfo.download_url} download={m.exportInfo.filename}>Download {m.exportInfo.filename}</a>
          )}
          {m.verification && <VerificationView v={m.verification} onOpenCitation={onOpenCitation} />}
        </div>
      )}
      {m.role === 'user' && m.sources && m.sources.length > 0 && (
        <div className="muted small">Sources: {m.sources.join(', ')}</div>
      )}
      {m.role === 'assistant' && !m.streaming && !m.error && !m.exportInfo && answer && (
        <div className="msg-footer muted small">
          {m.context && <span>Context {formatTokens(m.context.prompt_tokens)} / {formatTokens(m.context.context_size)} tokens</span>}
          {m.strategyInfo && m.strategyInfo.used === 'retrieval' && (
            <span title={m.strategyInfo.locators.join('\n')}>
              · {m.strategyInfo.passages} of {m.strategyInfo.passages_available} passages
            </span>
          )}
          {m.citationStats && (
            <span title={m.citationStats.unresolved.length ? 'Unmatched: ' + m.citationStats.unresolved.join(', ') : 'All citations point to real sections'}>
              · {m.citationStats.resolved}/{m.citationStats.total} citations verified
            </span>
          )}
          {m.sources && m.sources.length > 0 && (
            <button className="btn link small" onClick={() => onVerify(m)} disabled={m.verifying}>
              {m.verifying ? 'checking claims…' : m.verification ? 'fact-check again' : 'fact-check this answer'}
            </button>
          )}
          <span>· Download as:</span>
          {SAVE_KINDS.map((k) => (
            <button key={k.kind} className="btn link small" onClick={() => onSave(m, k.kind)}>{k.label}</button>
          ))}
        </div>
      )}
    </div>
  )
}
