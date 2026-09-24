import { useEffect, useState } from 'react'
import { api, RequestError } from '../services/api'
import type { LauncherSettings, LauncherStatus } from '../types/api'

interface Props {
  connected: boolean
  onChanged: () => void
  notify: (msg: string, kind?: 'error' | 'info') => void
}

const EMPTY: LauncherSettings = {
  server_path: '',
  model_path: '',
  mmproj_path: '',
  context_size: 16384,
  threads: 0,
  gpu_layers: 0,
  extra_args: '',
  reasoning_budget_off: false,
}

/**
 * Lets the user point the app at THEIR llama-server executable and GGUF model.
 * Paths are stored by the backend in data/llm_settings.json, never in source code,
 * so the project works on any machine after cloning.
 */
export function LauncherPanel({ connected, onChanged, notify }: Props) {
  const [status, setStatus] = useState<LauncherStatus | null>(null)
  const [form, setForm] = useState<LauncherSettings>(EMPTY)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [problems, setProblems] = useState<string[]>([])
  const [log, setLog] = useState<string[]>([])
  const [showLog, setShowLog] = useState(false)

  const refresh = async () => {
    try {
      const s = await api.launcherStatus()
      setStatus(s)
      setForm(s.settings)
      setLog(s.log_tail)
    } catch {
      /* backend offline */
    }
  }

  useEffect(() => { void refresh() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!connected && status && !status.settings.model_path) setOpen(true) }, [connected, status])

  const set = <K extends keyof LauncherSettings>(k: K, v: LauncherSettings[K]) => setForm((f) => ({ ...f, [k]: v }))

  const validate = async () => {
    try {
      const r = await api.launcherValidate(form)
      setProblems(r.problems)
      if (r.ok) notify('Paths look good: ' + r.command.slice(0, 1).join(''), 'info')
      return r.ok
    } catch (e) {
      notify((e as RequestError).message)
      return false
    }
  }

  const save = async () => {
    try {
      const s = await api.launcherSave(form)
      setStatus(s)
      notify('Model settings saved locally.', 'info')
    } catch (e) {
      notify((e as RequestError).message)
    }
  }

  const start = async () => {
    setBusy(true)
    setProblems([])
    try {
      const s = await api.launcherStart(form)
      setStatus(s)
      setLog(s.log_tail)
      notify('llama-server is starting – the model may take a moment to load.', 'info')
      // poll until the model is loaded
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const st = await api.llmStatus()
        if (st.connected) break
      }
      onChanged()
      await refresh()
    } catch (e) {
      const err = e as RequestError
      setProblems([err.message])
      if (err.logTail.length) { setLog(err.logTail); setShowLog(true) }
    } finally {
      setBusy(false)
    }
  }

  const stop = async () => {
    setBusy(true)
    try {
      const s = await api.launcherStop()
      setStatus(s)
      onChanged()
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(false)
    }
  }

  const running = !!status?.running

  return (
    <section className="col launcher">
      <header className="panel-header">
        <h2>Model launcher</h2>
        <div className="row tight">
          {running && <span className="badge green">running · pid {status?.pid}</span>}
          <button className="btn small" onClick={() => setOpen(!open)}>{open ? 'Hide' : running ? 'Manage' : 'Configure'}</button>
        </div>
      </header>

      {status?.foreign_server && (
        <div className="notice warn small">
          A llama-server that this app did not start is running on {status.host}:{status.port}
          {status.loaded_model ? <> with <strong>{status.loaded_model}</strong></> : null}.
          To load a different model, stop that server first (Ctrl-C in its terminal window), then start it here.
        </div>
      )}

      {!open && !running && (
        <div className="muted small">
          {status?.settings.model_path
            ? <>Configured model: <span className="mono">{fileName(status.settings.model_path)}</span></>
            : 'No model configured. Click Configure and enter the paths to your llama-server and .gguf model, or start llama-server yourself.'}
        </div>
      )}

      {open && (
        <div className="col">
          <div className="notice info small">
            Enter where <strong>you</strong> downloaded llama.cpp and a GGUF model. These paths are saved only on this
            computer (<span className="mono">{status?.settings_file ?? 'data/llm_settings.json'}</span>), not in the project source.
          </div>
          <label className="field">
            <span>llama-server executable</span>
            <input value={form.server_path} onChange={(e) => set('server_path', e.target.value)} placeholder="C:\llama.cpp\llama-server.exe  or  /usr/local/bin/llama-server" disabled={running} />
          </label>
          <label className="field">
            <span>Model file (.gguf)</span>
            <input value={form.model_path} onChange={(e) => set('model_path', e.target.value)} placeholder="C:\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf" disabled={running} />
          </label>
          <label className="field">
            <span>Vision projector (optional, enables figure analysis)</span>
            <input value={form.mmproj_path} onChange={(e) => set('mmproj_path', e.target.value)} placeholder="C:\\models\\mmproj-model-f16.gguf" disabled={running} />
          </label>
          <div className="row wrap">
            <label className="field grow">
              <span>Context size (-c)</span>
              <input type="number" min={512} step={1024} value={form.context_size} onChange={(e) => set('context_size', Number(e.target.value))} disabled={running} />
            </label>
            <label className="field grow">
              <span>Threads (0 = auto)</span>
              <input type="number" min={0} value={form.threads} onChange={(e) => set('threads', Number(e.target.value))} disabled={running} />
            </label>
            <label className="field grow">
              <span>GPU layers (-ngl)</span>
              <input type="number" min={0} value={form.gpu_layers} onChange={(e) => set('gpu_layers', Number(e.target.value))} disabled={running} />
            </label>
          </div>
          <label className="field">
            <span>Extra llama-server flags (optional)</span>
            <input value={form.extra_args} onChange={(e) => set('extra_args', e.target.value)} placeholder="--flash-attn on" disabled={running} />
          </label>
          <label className="check">
            <input type="checkbox" checked={form.reasoning_budget_off} onChange={(e) => set('reasoning_budget_off', e.target.checked)} disabled={running} />
            Disable thinking (<span className="mono">--reasoning-budget 0</span>, for Qwen3-style models)
          </label>
          <div className="muted small">Server binds to <span className="mono">{status?.host ?? '127.0.0.1'}:{status?.port ?? 8080}</span> (from LDW_LLM_BASE_URL).</div>

          {problems.length > 0 && (
            <div className="notice error small"><ul>{problems.map((p, i) => <li key={i}>{p}</li>)}</ul></div>
          )}

          <div className="row wrap">
            {!running ? (
              <>
                <button className="btn primary" onClick={start} disabled={busy || !form.server_path || !form.model_path}>{busy ? 'Starting…' : 'Start llama-server'}</button>
                <button className="btn" onClick={validate} disabled={busy}>Check paths</button>
                <button className="btn" onClick={save} disabled={busy}>Save</button>
              </>
            ) : (
              <button className="btn danger-btn" onClick={stop} disabled={busy}>{busy ? 'Stopping…' : 'Stop llama-server'}</button>
            )}
            <button className="btn link small" onClick={() => setShowLog(!showLog)}>{showLog ? 'hide log' : 'show log'}</button>
          </div>
          {showLog && <pre className="preview log">{log.length ? log.join('\n') : '(no log yet)'}</pre>}
        </div>
      )}
    </section>
  )
}

function fileName(p: string): string {
  return p.replace(/\\/g, '/').split('/').pop() ?? p
}
