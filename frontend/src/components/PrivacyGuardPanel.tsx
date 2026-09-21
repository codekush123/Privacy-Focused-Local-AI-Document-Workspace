import { useState } from 'react'
import { api, RequestError } from '../services/api'
import type { DocumentSummary, Finding, PiiCategory, RedactResult, ScanResult } from '../types/api'

interface Props {
  documents: DocumentSummary[]
  ready: boolean
  onDocumentsChanged: () => Promise<void>
  onExportCreated: () => Promise<void>
  notify: (msg: string, kind?: 'error' | 'info') => void
}

const CAT_LABEL: Record<PiiCategory, string> = {
  person: 'Person name', email: 'E-mail', phone: 'Phone', address: 'Address', organization: 'Organisation',
  id_number: 'ID number', iban: 'IBAN', credit_card: 'Card number', date_of_birth: 'Date of birth', ip_address: 'IP address', other: 'Other',
}

interface Row extends Finding { selected: boolean; replacement: string }

/**
 * Privacy Guard: find personal data (patterns + AI), review every finding,
 * then produce a redacted copy that can be exported or chatted with.
 */
export function PrivacyGuardPanel({ documents, ready, onDocumentsChanged, onExportCreated, notify }: Props) {
  const [chosenId, setDocId] = useState('')
  const docId = documents.some((d) => d.id === chosenId) ? chosenId : (documents[0]?.id ?? '')
  const [useAi, setUseAi] = useState(true)
  const [scan, setScan] = useState<ScanResult | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [busy, setBusy] = useState<'scan' | 'redact' | null>(null)
  const [exportKind, setExportKind] = useState('docx')
  const [addToLibrary, setAddToLibrary] = useState(true)
  const [result, setResult] = useState<RedactResult | null>(null)
  const [custom, setCustom] = useState('')
  const [customCat, setCustomCat] = useState<PiiCategory>('person')

  const runScan = async () => {
    if (!docId) return
    setBusy('scan'); setScan(null); setRows([]); setResult(null)
    try {
      const s = await api.privacyScan(docId, useAi && ready)
      setScan(s)
      setRows(s.findings.map((f) => ({ ...f, selected: true, replacement: '' })))
      if (s.ai_error) notify('AI detection failed, showing pattern matches only: ' + s.ai_error)
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(null)
    }
  }

  const addCustom = () => {
    const t = custom.trim()
    if (!t) return
    setRows((r) => [...r, { text: t, category: customCat, count: 0, detected_by: 'pattern', reason: 'added by you', context: '', selected: true, replacement: '' }])
    setCustom('')
  }

  const redact = async () => {
    const items = rows.filter((r) => r.selected).map((r) => ({ text: r.text, category: r.category, replacement: r.replacement }))
    if (!items.length) { notify('Select at least one item to redact.'); return }
    setBusy('redact')
    try {
      const res = await api.privacyRedact(docId, items, exportKind, addToLibrary)
      setResult(res)
      if (res.document) await onDocumentsChanged()
      if (res.export) await onExportCreated()
      notify(`Redacted ${Object.keys(res.replacements).length} item(s).`, 'info')
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(null)
    }
  }

  const setRow = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const selectedCount = rows.filter((r) => r.selected).length

  return (
    <section className="panel privacy-guard">
      <header className="panel-header">
        <h2>Privacy Guard</h2>
        <span className="muted small">find and redact personal data before sharing</span>
      </header>

      {documents.length === 0 ? (
        <div className="muted">Import a document to scan it for personal data (names, e-mails, phone numbers, IDs, IBANs, card numbers, addresses).</div>
      ) : (
        <>
          <div className="row gap wrap">
            <label className="field"><span>Document</span>
              <select value={docId} onChange={(e) => { setDocId(e.target.value); setScan(null); setRows([]); setResult(null) }}>
                {documents.map((d) => <option key={d.id} value={d.id}>{d.display_name}</option>)}
              </select>
            </label>
            <label className="row gap-s small self-end"><input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} disabled={!ready} />
              also use the local AI to find names and addresses{!ready && ' (llama-server offline)'}</label>
            <button className="btn primary self-end" onClick={runScan} disabled={busy === 'scan' || !docId}>{busy === 'scan' ? 'Scanning…' : 'Scan for personal data'}</button>
          </div>

          {scan && (
            <>
              <div className="muted small">
                {rows.length === 0 ? 'No personal data found.' : `${rows.length} finding(s) in ${scan.document_name}`}
                {scan.ai_used ? ' · pattern + AI detection' : ' · pattern detection only'}
              </div>
              {rows.length > 0 && (
                <div className="table-wrap">
                  <table className="claims pii">
                    <thead><tr><th></th><th>Found text</th><th>Category</th><th>Where</th><th>Replace with</th></tr></thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={i} className={r.selected ? '' : 'dim'}>
                          <td><input type="checkbox" checked={r.selected} onChange={(e) => setRow(i, { selected: e.target.checked })} /></td>
                          <td><code>{r.text}</code>{r.count > 1 && <span className="muted small"> ×{r.count}</span>}</td>
                          <td>
                            <select value={r.category} onChange={(e) => setRow(i, { category: e.target.value as PiiCategory })}>
                              {(Object.keys(CAT_LABEL) as PiiCategory[]).map((c) => <option key={c} value={c}>{CAT_LABEL[c]}</option>)}
                            </select>
                            <div className="muted small">{r.detected_by === 'ai' ? 'AI' : 'pattern'}{r.reason ? ` · ${r.reason}` : ''}</div>
                          </td>
                          <td className="small muted ctx">{r.context}</td>
                          <td><input value={r.replacement} onChange={(e) => setRow(i, { replacement: e.target.value })} placeholder="auto e.g. [PERSON-1]" /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="row gap wrap">
                <input className="grow" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Add text the scan missed…" onKeyDown={(e) => e.key === 'Enter' && addCustom()} />
                <select value={customCat} onChange={(e) => setCustomCat(e.target.value as PiiCategory)}>
                  {(Object.keys(CAT_LABEL) as PiiCategory[]).map((c) => <option key={c} value={c}>{CAT_LABEL[c]}</option>)}
                </select>
                <button className="btn small" onClick={addCustom}>Add</button>
              </div>
              <div className="row gap wrap redact-row">
                <label className="row gap-s small"><input type="checkbox" checked={addToLibrary} onChange={(e) => setAddToLibrary(e.target.checked)} />add redacted copy to the library (chat with it safely)</label>
                <label className="row gap-s small">export as
                  <select value={exportKind} onChange={(e) => setExportKind(e.target.value)}>
                    {[['docx', 'Word'], ['pdf', 'PDF'], ['md', 'Markdown'], ['txt', 'Text'], ['none', 'no file']].map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </label>
                <button className="btn primary" onClick={redact} disabled={busy === 'redact' || selectedCount === 0}>
                  {busy === 'redact' ? 'Redacting…' : `Redact ${selectedCount} item(s)`}
                </button>
              </div>
            </>
          )}

          {result && (
            <div className="redact-result">
              <div className="notice ok small">
                Redaction done. {result.document && <>Added <strong>{result.document.display_name}</strong> to the library. </>}
                {result.export && <a className="btn small" href={result.export.download_url} download={result.export.filename}>Download {result.export.filename}</a>}
              </div>
              <details className="small"><summary>Replacements</summary>
                <ul>{Object.entries(result.replacements).map(([k, v]) => <li key={k}><code>{k}</code> → <code>{v}</code></li>)}</ul>
              </details>
              <details className="small"><summary>Preview of redacted text</summary><pre className="preview">{result.preview}</pre></details>
            </div>
          )}
        </>
      )}
    </section>
  )
}
