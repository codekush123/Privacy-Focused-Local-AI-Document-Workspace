import { useRef, useState } from 'react'
import { api, formatBytes, RequestError } from '../services/api'
import type { DocumentSummary } from '../types/api'

interface Props {
  documents: DocumentSummary[]
  selected: Set<string>
  onToggle: (id: string) => void
  onSelectAll: (all: boolean) => void
  onChanged: () => Promise<void>
  supported: string[]
  notify: (msg: string, kind?: 'error' | 'info') => void
}

export function DocumentPanel({ documents, selected, onToggle, onSelectAll, onChanged, supported, notify }: Props) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [mode, setMode] = useState<'none' | 'url' | 'text'>('none')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [textName, setTextName] = useState('')
  const [preview, setPreview] = useState<{ name: string; md: string } | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFiles = async (files: FileList | File[]) => {
    const list = Array.from(files)
    for (const f of list) {
      setBusy(`Importing ${f.name}…`)
      try {
        await api.upload(f)
      } catch (e) {
        notify(`${f.name}: ${(e as RequestError).message}`)
      }
    }
    setBusy(null)
    await onChanged()
  }

  const importUrl = async () => {
    if (!url.trim()) return
    setBusy('Fetching the page…')
    try {
      await api.importUrl(url.trim())
      setUrl(''); setMode('none'); await onChanged()
    } catch (e) { notify((e as RequestError).message) } finally { setBusy(null) }
  }

  const importText = async () => {
    if (!text.trim()) return
    setBusy('Adding text…')
    try {
      await api.importText(text, textName.trim() || undefined)
      setText(''); setTextName(''); setMode('none'); await onChanged()
    } catch (e) { notify((e as RequestError).message) } finally { setBusy(null) }
  }

  const remove = async (d: DocumentSummary) => {
    try { await api.deleteDocument(d.id); await onChanged() } catch (e) { notify((e as RequestError).message) }
  }

  const clearAll = async () => {
    if (!documents.length || !confirm('Remove all imported documents and their converted content?')) return
    try { await api.clearDocuments(); await onChanged() } catch (e) { notify((e as RequestError).message) }
  }

  const showPreview = async (d: DocumentSummary) => {
    try {
      setPreview({ name: d.display_name, md: (await api.documentPreview(d.id, 6000)).full_markdown })
    } catch (e) { notify((e as RequestError).message) }
  }

  const allSelected = documents.length > 0 && documents.every((d) => selected.has(d.id))

  return (
    <section className="card">
      <header>
        <h2>Sources</h2>
        <span className="dim tiny">{selected.size}/{documents.length} selected</span>
      </header>

      <div
        className={`dropzone ${dragOver ? 'over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); void handleFiles(e.dataTransfer.files) }}
        onClick={() => fileInput.current?.click()}
        role="button"
        tabIndex={0}
      >
        <strong>Drop files or click to upload</strong>
        <span>PDF · Word · PowerPoint · Excel · CSV · HTML · text</span>
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          accept={supported.map((s) => '.' + s).join(',')}
          onChange={(e) => { if (e.target.files) void handleFiles(e.target.files); e.target.value = '' }}
        />
      </div>

      <div className="row tight">
        <button className="btn small" onClick={() => setMode(mode === 'url' ? 'none' : 'url')}>Web page</button>
        <button className="btn small" onClick={() => setMode(mode === 'text' ? 'none' : 'text')}>Paste text</button>
      </div>

      {mode === 'url' && (
        <div className="col">
          <div className="notice warn tiny">
            Fetching a URL is the one step that uses the network. The page is downloaded once and then parsed locally.
          </div>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.org/article"
            onKeyDown={(e) => e.key === 'Enter' && importUrl()} />
          <button className="btn primary small" onClick={importUrl} disabled={!url.trim() || !!busy}>Fetch and import</button>
        </div>
      )}
      {mode === 'text' && (
        <div className="col">
          <input value={textName} onChange={(e) => setTextName(e.target.value)} placeholder="Name (optional)" />
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="Paste text…" />
          <button className="btn primary small" onClick={importText} disabled={!text.trim() || !!busy}>Add</button>
        </div>
      )}

      {busy && <div className="notice info tiny">{busy}</div>}

      {documents.length > 0 && (
        <div className="row between tiny">
          <label className="check"><input type="checkbox" checked={allSelected} onChange={(e) => onSelectAll(e.target.checked)} />Select all</label>
          <button className="btn link danger small" onClick={clearAll}>Clear all</button>
        </div>
      )}

      <ul className="doc-list">
        {documents.length === 0 && <li className="empty-hint">No documents yet.</li>}
        {documents.map((d) => (
          <li key={d.id} className={`doc ${selected.has(d.id) ? 'selected' : ''}`}>
            <label className="doc-top">
              <input type="checkbox" checked={selected.has(d.id)} onChange={() => onToggle(d.id)} disabled={d.status !== 'ready'} />
              <span className={`tag t-${d.source_type}`}>{d.source_type.toUpperCase()}</span>
              <span className="doc-name" title={d.original_filename}>{d.display_name}</span>
            </label>
            <div className="doc-meta">
              <span>{formatBytes(d.size_bytes)}</span>
              <span>· {d.section_count} {sectionWord(d)}</span>
              <span>· {(d.character_count / 1000).toFixed(1)}k chars</span>
              {typeof d.metadata?.figures_described === 'number' && d.metadata.figures_described > 0 && (
                <span>· {d.metadata.figures_described as number} figure(s) read</span>
              )}
            </div>
            {d.error && <div className="tiny danger-text">{d.error}</div>}
            <div className="doc-actions">
              <button className="btn link small" onClick={() => showPreview(d)}>preview</button>
              <button className="btn link danger small" onClick={() => remove(d)}>remove</button>
            </div>
          </li>
        ))}
      </ul>

      {preview && (
        <div className="modal-backdrop" onClick={() => setPreview(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <header>
              <h3>{preview.name}</h3>
              <button className="btn small" onClick={() => setPreview(null)}>Close</button>
            </header>
            <p className="small muted" style={{ margin: 0 }}>Normalized Markdown – exactly what the model receives (first 6,000 characters).</p>
            <pre className="preview">{preview.md}</pre>
          </div>
        </div>
      )}
    </section>
  )
}

function sectionWord(d: DocumentSummary): string {
  switch (d.source_type) {
    case 'pdf': return d.section_count === 1 ? 'page' : 'pages'
    case 'pptx': return d.section_count === 1 ? 'slide' : 'slides'
    case 'xlsx': return d.section_count === 1 ? 'sheet' : 'sheets'
    default: return d.section_count === 1 ? 'section' : 'sections'
  }
}
