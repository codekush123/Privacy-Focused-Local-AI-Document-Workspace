import { useCallback, useEffect, useState } from 'react'
import { AgentPanel } from '../components/AgentPanel'
import { ChatPanel } from '../components/ChatPanel'
import { DataPanel } from '../components/DataPanel'
import { DocumentPanel } from '../components/DocumentPanel'
import { FiguresPanel } from '../components/FiguresPanel'
import { PrivacyGuardPanel } from '../components/PrivacyGuardPanel'
import { ContextCard, ExportsCard } from '../components/StatusPanels'
import { StudyPanel } from '../components/StudyPanel'
import { TopBar } from '../components/TopBar'
import { api } from '../services/api'
import type { ContextCheck, DocumentSummary, ExportInfo, LlmStatus, PrivacyStatus } from '../types/api'

interface Toast { id: number; msg: string; kind: 'error' | 'info' }

type Tab = 'agent' | 'chat' | 'figures' | 'study' | 'data' | 'privacy'

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'agent', label: 'Agent', hint: 'one request, routed to the right tool and fact-checked' },
  { id: 'chat', label: 'Chat', hint: 'ask, cite, fact-check, export' },
  { id: 'figures', label: 'Figures', hint: 'read charts and images with a vision model' },
  { id: 'study', label: 'Study', hint: 'AI quiz with tutor grading' },
  { id: 'data', label: 'Data', hint: 'CSV / Excel questions with exact answers' },
  { id: 'privacy', label: 'Privacy Guard', hint: 'find and redact personal data' },
]

export function Workspace() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [exports, setExports] = useState<ExportInfo[]>([])
  const [llm, setLlm] = useState<LlmStatus | null>(null)
  const [privacy, setPrivacy] = useState<PrivacyStatus | null>(null)
  const [context, setContext] = useState<ContextCheck | null>(null)
  const [supported, setSupported] = useState<string[]>([])
  const [backendUp, setBackendUp] = useState(true)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [tab, setTabState] = useState<Tab>(() => (TABS.some((t) => t.id === location.hash.slice(1)) ? (location.hash.slice(1) as Tab) : 'chat'))
  const setTab = (t: Tab) => { setTabState(t); history.replaceState(null, '', '#' + t) }

  const notify = useCallback((msg: string, kind: 'error' | 'info' = 'error') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, msg, kind }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 8000 : 4000)
  }, [])

  const refreshDocuments = useCallback(async () => {
    try {
      const docs = await api.listDocuments()
      setDocuments(docs)
      // Drop deleted ids; auto-select newly imported documents so they are immediately usable.
      setSelected((s) => {
        const next = new Set([...s].filter((id) => docs.some((d) => d.id === id)))
        for (const d of docs) if (d.status === 'ready' && !s.has(d.id) && isNew(d)) next.add(d.id)
        return next
      })
      setBackendUp(true)
    } catch {
      setBackendUp(false)
    }
  }, [])

  const refreshExports = useCallback(async () => {
    try { setExports(await api.listExports()) } catch { /* backend offline */ }
  }, [])

  const refreshStatus = useCallback(async () => {
    try {
      const [l, p] = await Promise.all([api.llmStatus(), api.privacy()])
      setLlm(l)
      setPrivacy(p)
      setBackendUp(true)
    } catch {
      setBackendUp(false)
      setLlm(null)
    }
  }, [])

  useEffect(() => {
    void refreshDocuments()
    void refreshExports()
    void refreshStatus()
    api.supported().then((s) => setSupported(s.extensions)).catch(() => {})
    const t = setInterval(() => void refreshStatus(), 20000)
    return () => clearInterval(t)
  }, [refreshDocuments, refreshExports, refreshStatus])

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  const selectAll = (all: boolean) => setSelected(all ? new Set(documents.filter((d) => d.status === 'ready').map((d) => d.id)) : new Set())
  const selectedIds = documents.filter((d) => selected.has(d.id)).map((d) => d.id)
  const ready = !!llm?.connected && (llm?.ai_requests_allowed ?? true)

  return (
    <div className="app">
      <TopBar llm={llm} privacy={privacy} backendUp={backendUp} onChanged={() => void refreshStatus()} notify={notify} />

      <main className="layout">
        <aside className="side left">
          <DocumentPanel
            documents={documents}
            selected={selected}
            onToggle={toggle}
            onSelectAll={selectAll}
            onChanged={refreshDocuments}
            supported={supported}
            notify={notify}
          />
        </aside>

        <div className="main">
          <nav className="tabs">
            {TABS.map((t) => (
              <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)} title={t.hint}>{t.label}</button>
            ))}
          </nav>

          {/* Chat stays mounted so a running answer is not lost when switching tabs. */}
          <div className={tab === 'chat' ? 'main' : 'hidden'}>
            <ChatPanel
              documents={documents}
              selectedIds={selectedIds}
              aiAllowed={llm?.ai_requests_allowed ?? true}
              connected={!!llm?.connected}
              onContext={setContext}
              onExportCreated={refreshExports}
              notify={notify}
            />
          </div>
          {tab === 'agent' && (
            <AgentPanel
              documents={documents}
              selectedIds={selectedIds}
              ready={ready}
              onExportCreated={refreshExports}
              onGoToTab={(t) => setTab(t as Tab)}
              notify={notify}
            />
          )}
          {tab === 'figures' && <FiguresPanel documents={documents} onDocumentsChanged={refreshDocuments} notify={notify} />}
          {tab === 'study' && <StudyPanel documents={documents} selectedIds={selectedIds} ready={ready} onExportCreated={refreshExports} notify={notify} />}
          {tab === 'data' && <DataPanel documents={documents} ready={ready} onExportCreated={refreshExports} notify={notify} />}
          {tab === 'privacy' && <PrivacyGuardPanel documents={documents} ready={ready} onDocumentsChanged={refreshDocuments} onExportCreated={refreshExports} notify={notify} />}
        </div>

        <aside className="side right">
          <ContextCard llm={llm} context={context} selectedCount={selectedIds.length} />
          <ExportsCard exports={exports} onChanged={refreshExports} notify={notify} />
        </aside>
      </main>

      <div className="toasts">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
      </div>
    </div>
  )
}

const seen = new Set<string>()
function isNew(d: DocumentSummary): boolean {
  if (seen.has(d.id)) return false
  seen.add(d.id)
  // Documents restored from disk on first load are not auto-selected.
  return Date.now() - new Date(d.imported_at).getTime() < 60_000
}
