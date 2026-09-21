import { useRef, useState } from 'react'
import { api, formatBytes, formatTokens, RequestError } from '../services/api'
import type { DocumentSummary } from '../types/api'

const TYPE_LABEL: Record<string, string> = {
  text: 'TEXT', txt: 'TXT', md: 'MD', html: 'HTML', url: 'URL', csv: 'CSV',
  docx: 'DOCX', pdf: 'PDF', xlsx: 'XLSX', pptx: 'PPTX',
}

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
    if (!list.length) return
    for (const f of list) {
      setBusy(`Importing ${f.name}…`)
      try {
        await api.upload(f)
      } catch (e) {
        notify(`${f.name}: ${(e as RequestError).message}`, 'error')
      }
    }
    setBusy(null)
    await onChanged()
  }

  const importUrl = async () => {
    if (!url.trim()) return
    setBusy('Fetching URL (network)…')
    try {
      await api.importUrl(url.trim())
      setUrl('')
      setMode('none')
      await onChanged()
    } catch (e) {
      notify((e as RequestError).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  const importText = async () => {
    if (!text.trim()) return
    setBusy('Adding text…')
    try {
      await api.importText(text, textName.trim() || undefined)
      setText('')
      setTextName('')
      setMode('none')
      await onChanged()
    } catch (e) {
      notify((e as RequestError).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  const remove = async (d: DocumentSummary) => {
    try {
      await api.deleteDocument(d.id)
      await onChanged()
    } catch (e) {
      notify((e as RequestError).message, 'error')
    }
  }

  const clearAll = async () => {
    if (!documents.length || !confirm('Remove all imported documents and their converted content?')) return
    try {
      await api.clearDocuments()
      await onChanged()
    } catch (e) {
      notify((e as RequestError).message, 'error')
    }
  }

  const showPreview = async (d: DocumentSummary) => {
    try {
      const p = await api.documentPreview(d.id, 6000)
      setPreview({ name: d.display_name, md: p.full_markdown })
    } catch (e) {
      notify((e as RequestError).message, 'error')
    }
  }

  const allSelected = documents.length > 0 && documents.every((d) => selected.has(d.id))

  return (
    <section className="panel documents">
      <header className="panel-header">
        <h2>Documents</h2>
        <span className="muted small">{selected.size}/{documents.length} selected</span>
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
        <strong>Upload files</strong>
        <span className="muted small">drag &amp; drop or click · {supported.join(', ')}</span>
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          accept={supported.map((s) => '.' + s).join(',')}
          onChange={(e) => { if (e.target.files) void handleFiles(e.target.files); e.target.value = '' }}
        />
      </div>

      <div className="row gap">
        <button className="btn small" onClick={() => setMode(mode === 'url' ? 'none' : 'url')}>Import URL</button>
        <button className="btn small" onClick={() => setMode(mode === 'text' ? 'none' : 'text')}>Paste text</button>
      </div>

      {mode === 'url' && (
        <div className="subform">
          <div className="notice network">
            <strong>Network operation.</strong> Fetching this URL requires contacting the website. The downloaded content
            will still be parsed and analyzed locally. Only http(s) URLs are accepted and only this page is fetched.
          </div>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.org/article" onKeyDown={(e) => e.key === 'Enter' && importUrl()} />
          <button className="btn primary small" onClick={importUrl} disabled={!url.trim() || !!busy}>Fetch and import</button>
        </div>
      )}
      {mode === 'text' && (
        <div className="subform">
          <input value={textName} onChange={(e) => setTextName(e.target.value)} placeholder="Name (optional)" />
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} placeholder="Paste or type text…" />
          <button className="btn primary small" onClick={importText} disabled={!text.trim() || !!busy}>Add as document</button>
        </div>
      )}

      {busy && <div className="notice info">{busy}</div>}

      {documents.length > 0 && (
        <div className="row between small">
          <label className="row gap-s"><input type="checkbox" checked={allSelected} onChange={(e) => onSelectAll(e.target.checked)} /> Select all</label>
          <button className="btn link danger" onClick={clearAll}>Clear all documents</button>
        </div>
      )}

      <ul className="doc-list">
        {documents.length === 0 && <li className="muted small empty">No documents yet. Upload a PDF, DOCX, PPTX, XLSX, CSV, HTML, TXT or MD file.</li>}
        {documents.map((d) => (
          <li key={d.id} className={`doc ${selected.has(d.id) ? 'selected' : ''} ${d.status}`}>
            <label className="doc-main">
              <input type="checkbox" checked={selected.has(d.id)} onChange={() => onToggle(d.id)} disabled={d.status !== 'ready'} />
              <span className={`tag t-${d.source_type}`}>{TYPE_LABEL[d.source_type] ?? d.source_type}</span>
              <span className="doc-name" title={d.original_filename}>{d.display_name}</span>
            </label>
            <div className="doc-meta muted small">
              <span>{d.status === 'ready' ? 'ready' : 'error'}</span>
              <span>· {formatBytes(d.size_bytes)}</span>
              <span>· {d.character_count.toLocaleString()} chars</span>
              {d.token_count != null && <span>· {formatTokens(d.token_count)} tok</span>}
              <span>· {d.section_count} {sectionWord(d)}</span>
            </div>
            {d.error && <div className="small danger-text">{d.error}</div>}
            <div className="doc-actions">
              <button className="btn link small" onClick={() => showPreview(d)}>preview</button>
              <button className="btn link small danger" onClick={() => remove(d)}>remove</button>
            </div>
          </li>
        ))}
      </ul>

      {preview && (
        <div className="modal-backdrop" onClick={() => setPreview(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <header className="row between">
              <strong>{preview.name}</strong>
              <button className="btn small" onClick={() => setPreview(null)}>Close</button>
            </header>
            <p className="muted small">Normalized Markdown (first 6,000 characters) – this is what the model receives.</p>
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
