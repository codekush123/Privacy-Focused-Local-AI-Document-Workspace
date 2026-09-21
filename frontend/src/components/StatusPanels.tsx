import { api, formatBytes, formatTokens, RequestError } from '../services/api'
import type { ContextCheck, ExportInfo, LlmStatus, PrivacyStatus } from '../types/api'

// ------------------------------------------------------------- Privacy ---
export function PrivacyBadge({ privacy, llm }: { privacy: PrivacyStatus | null; llm: LlmStatus | null }) {
  if (!privacy) return <div className="panel privacy muted small">Privacy status unavailable (backend offline).</div>
  const ok = privacy.local_only && privacy.llm_endpoint_is_local
  return (
    <section className={`panel privacy ${ok ? 'ok' : 'warn'}`}>
      <header className="panel-header">
        <h2>Privacy</h2>
        <span className={`badge ${ok ? 'green' : 'red'}`}>{privacy.mode}</span>
      </header>
      <dl className="kv">
        <dt>Privacy</dt><dd>{ok ? 'LOCAL' : 'NOT LOCAL'}</dd>
        <dt>LLM</dt><dd>{privacy.llm_runtime}</dd>
        <dt>Endpoint</dt><dd className="mono">{privacy.llm_endpoint.replace(/^https?:\/\//, '')}</dd>
        <dt>Model</dt><dd>{llm?.model_name ?? '–'}</dd>
        <dt>Network needed</dt><dd>{privacy.network_needed}</dd>
        <dt>Cloud AI APIs</dt><dd>{privacy.cloud_ai_apis ? 'yes' : 'none'}</dd>
        <dt>Telemetry</dt><dd>{privacy.telemetry ? 'yes' : 'none'}</dd>
      </dl>
      <ul className="notes small muted">
        {privacy.notes.map((n, i) => <li key={i} className={n.startsWith('WARNING') || n.includes('DISABLED') ? 'danger-text' : ''}>{n}</li>)}
      </ul>
      <div className="muted small">Data directory: <span className="mono">{privacy.data_dir}</span></div>
    </section>
  )
}

// --------------------------------------------------------------- Model ---
export function ModelPanel({ llm, context, onRefresh }: { llm: LlmStatus | null; context: ContextCheck | null; onRefresh: () => void }) {
  const connected = !!llm?.connected
  const used = context?.prompt_tokens ?? 0
  const total = llm?.context_size ?? context?.context_size ?? 0
  const allowed = llm?.allowed_prompt_tokens ?? context?.allowed_prompt_tokens ?? 0
  const pct = total ? Math.min(100, Math.round((used / total) * 100)) : 0
  const over = context ? !context.fits : false
  return (
    <section className="panel model">
      <header className="panel-header">
        <h2>Model</h2>
        <span className={`badge ${connected ? 'green' : 'red'}`}>{connected ? 'connected' : 'disconnected'}</span>
      </header>
      <dl className="kv">
        <dt>Server</dt><dd>llama-server</dd>
        <dt>Endpoint</dt><dd className="mono">{llm?.endpoint ?? '–'}</dd>
        <dt>Model</dt><dd title={llm?.model_path ?? ''}>{llm?.model_name ?? '–'}</dd>
        <dt>Active context</dt><dd>{formatTokens(llm?.context_size)} tokens</dd>
        {llm?.train_context_size ? <><dt>Trained context</dt><dd>{formatTokens(llm.train_context_size)} tokens</dd></> : null}
        <dt>Reserved for answer</dt><dd>{formatTokens(llm?.max_output_tokens)} + {formatTokens(llm?.safety_reserve)} safety</dd>
        <dt>Prompt budget</dt><dd>{formatTokens(allowed)} tokens</dd>
      </dl>
      {!connected && llm?.error && <div className="notice error small">{llm.error}</div>}
      {connected && (
        <div className="context-usage">
          <div className="row between small">
            <span>Context usage</span>
            <span className={over ? 'danger-text' : ''}>{formatTokens(used)} / {formatTokens(total)} tokens</span>
          </div>
          <div className="bar"><div className={`fill ${over ? 'over' : ''}`} style={{ width: `${pct}%` }} /></div>
          {context && (
            <div className={`small ${over ? 'danger-text' : 'muted'}`}>{context.message}</div>
          )}
        </div>
      )}
      <button className="btn small" onClick={onRefresh}>Refresh status</button>
    </section>
  )
}

// ------------------------------------------------------------- Exports ---
const KIND_LABEL: Record<string, string> = { docx: 'Word', xlsx: 'Excel', pptx: 'PowerPoint', csv: 'CSV', md: 'Markdown', txt: 'Text', pdf: 'PDF', tex: 'LaTeX' }

export function ExportsPanel({ exports, onChanged, notify }: { exports: ExportInfo[]; onChanged: () => Promise<void>; notify: (m: string, k?: 'error' | 'info') => void }) {
  const remove = async (e: ExportInfo) => {
    try { await api.deleteExport(e.id); await onChanged() } catch (err) { notify((err as RequestError).message, 'error') }
  }
  const clear = async () => {
    if (!exports.length || !confirm('Delete all generated files?')) return
    try { await api.clearExports(); await onChanged() } catch (err) { notify((err as RequestError).message, 'error') }
  }
  return (
    <section className="panel exports">
      <header className="panel-header">
        <h2>Exports</h2>
        {exports.length > 0 && <button className="btn link danger small" onClick={clear}>Clear generated files</button>}
      </header>
      {exports.length === 0 && <div className="muted small">No generated files yet. Use “Generate Word / Excel / PowerPoint” in the chat.</div>}
      <ul className="export-list">
        {exports.map((e) => (
          <li key={e.id}>
            <span className={`tag t-${e.kind}`}>{KIND_LABEL[e.kind] ?? e.kind}</span>
            <a className="export-name" href={e.download_url} download={e.filename} title={e.prompt}>{e.filename}</a>
            <span className="muted small">{formatBytes(e.size_bytes)}</span>
            <a className="btn small" href={e.download_url} download={e.filename}>Download</a>
            <button className="btn link danger small" onClick={() => remove(e)}>✕</button>
          </li>
        ))}
      </ul>
    </section>
  )
}
