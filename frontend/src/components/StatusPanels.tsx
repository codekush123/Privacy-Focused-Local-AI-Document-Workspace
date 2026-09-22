import { api, formatBytes, formatTokens, RequestError } from '../services/api'
import type { ContextCheck, ExportInfo, LlmStatus } from '../types/api'

/** Compact context meter: how much of the model's window the selection uses. */
export function ContextCard({ llm, context, selectedCount }: {
  llm: LlmStatus | null
  context: ContextCheck | null
  selectedCount: number
}) {
  const total = llm?.context_size ?? context?.context_size ?? 0
  const used = context?.prompt_tokens ?? 0
  const allowed = llm?.allowed_prompt_tokens ?? context?.allowed_prompt_tokens ?? 0
  const pct = total ? Math.min(100, Math.round((used / total) * 100)) : 0
  const over = context ? !context.fits : false
  // Reading the prompt is the slow part on a CPU machine - show the wait up front.
  const readSpeed = llm?.prompt_tokens_per_second ?? null
  const readSeconds = readSpeed && used ? Math.round(used / readSpeed) : null

  return (
    <section className="card">
      <header><h2>Context</h2>{over && <span className="badge bad">too large</span>}</header>

      {!llm?.connected ? (
        <p className="small muted" style={{ margin: 0 }}>Connect llama-server to see how much of the context window your selection uses.</p>
      ) : (
        <>
          <div className="row between small">
            <span className="muted">{selectedCount} document{selectedCount === 1 ? '' : 's'} selected</span>
            <span className={over ? 'danger-text' : 'muted'}>{formatTokens(used)} / {formatTokens(total)}</span>
          </div>
          <div className={`meter ${over ? 'over' : ''}`}><span style={{ width: `${pct}%` }} /></div>
          <div className="tiny dim">
            {formatTokens(allowed)} tokens available for documents; {formatTokens(llm.max_output_tokens)} reserved for the answer.
          </div>
          {readSeconds !== null && readSeconds > 5 && (
            <div className={`notice ${readSeconds > 90 ? 'warn' : 'info'} tiny`}>
              The model needs about <strong>{humanize(readSeconds)}</strong> just to read this selection before it starts
              answering ({readSpeed} tok/s on this machine).
              {readSeconds > 90 && ' Select fewer documents or use a smaller model to speed this up.'}
            </div>
          )}
          {over && context && (
            <div className="notice error">
              {context.message}
              <ul>{context.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          )}
          {llm.speed_warning && <div className="notice warn tiny">{llm.speed_warning}</div>}
        </>
      )}
    </section>
  )
}

function humanize(seconds: number): string {
  if (seconds < 60) return `${seconds} seconds`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s ? `${m} min ${s} s` : `${m} minute${m === 1 ? '' : 's'}`
}

const KIND_LABEL: Record<string, string> = {
  docx: 'Word', xlsx: 'Excel', pptx: 'PowerPoint', csv: 'CSV',
  md: 'Markdown', txt: 'Text', pdf: 'PDF', tex: 'LaTeX',
}

export function ExportsCard({ exports, onChanged, notify }: {
  exports: ExportInfo[]
  onChanged: () => Promise<void>
  notify: (m: string, k?: 'error' | 'info') => void
}) {
  const remove = async (e: ExportInfo) => {
    try { await api.deleteExport(e.id); await onChanged() } catch (err) { notify((err as RequestError).message) }
  }
  const clear = async () => {
    if (!exports.length || !confirm('Delete all generated files?')) return
    try { await api.clearExports(); await onChanged() } catch (err) { notify((err as RequestError).message) }
  }

  return (
    <section className="card">
      <header>
        <h2>Files</h2>
        {exports.length > 0 && <button className="btn link danger small" onClick={clear}>clear</button>}
      </header>
      {exports.length === 0 ? (
        <p className="small muted" style={{ margin: 0 }}>Generated Word, Excel, PowerPoint and PDF files appear here.</p>
      ) : (
        <ul className="export-list">
          {exports.map((e) => (
            <li key={e.id}>
              <span className={`tag t-${e.kind}`}>{KIND_LABEL[e.kind] ?? e.kind}</span>
              <a className="export-name" href={e.download_url} download={e.filename} title={e.prompt}>{e.filename}</a>
              <span className="dim tiny">{formatBytes(e.size_bytes)}</span>
              <button className="btn link danger small" onClick={() => remove(e)} aria-label="Delete">✕</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
