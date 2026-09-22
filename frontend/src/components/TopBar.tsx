import { useState } from 'react'
import { formatTokens } from '../services/api'
import type { LlmStatus, PrivacyStatus } from '../types/api'
import { LauncherPanel } from './LauncherPanel'

interface Props {
  llm: LlmStatus | null
  privacy: PrivacyStatus | null
  backendUp: boolean
  onChanged: () => void
  notify: (msg: string, kind?: 'error' | 'info') => void
}

/**
 * Slim header: the three facts that matter at a glance (privacy mode, model,
 * connection). Detail lives behind a click so the workspace stays uncluttered.
 */
export function TopBar({ llm, privacy, backendUp, onChanged, notify }: Props) {
  const [open, setOpen] = useState<'privacy' | 'model' | null>(null)
  const local = !!privacy?.local_only && !!privacy?.llm_endpoint_is_local
  const connected = !!llm?.connected

  return (
    <header className="topbar">
      <div className="brand">
        <h1>Local AI Document Workspace</h1>
        <small>everything runs on this computer</small>
      </div>
      <span className="grow" />

      {!backendUp && <span className="badge bad"><span className="dot" />backend offline</span>}

      <button className={`badge button ${local ? 'good' : 'bad'}`} onClick={() => setOpen('privacy')} title="Privacy details">
        <span className="dot" />{local ? 'Local only' : 'Check privacy'}
      </button>

      <button className={`badge button ${connected ? 'plain' : 'bad'}`} onClick={() => setOpen('model')} title="Model and server settings">
        {connected
          ? <>{shortModel(llm?.model_name)} · {formatTokens(llm?.context_size)} ctx</>
          : <><span className="dot" />no model</>}
      </button>

      <button className="btn icon" onClick={() => setOpen('model')} aria-label="Settings">⚙</button>

      {open === 'privacy' && <PrivacyDialog privacy={privacy} llm={llm} onClose={() => setOpen(null)} />}
      {open === 'model' && (
        <div className="modal-backdrop" onClick={() => setOpen(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <header>
              <h3>Model</h3>
              <button className="btn small" onClick={() => setOpen(null)}>Close</button>
            </header>
            <ModelFacts llm={llm} />
            <LauncherPanel connected={llm ? llm.connected : true} onChanged={onChanged} notify={notify} />
          </div>
        </div>
      )}
    </header>
  )
}

function shortModel(name?: string | null): string {
  if (!name) return 'model'
  return name.replace(/\.gguf$/i, '').replace(/-(Q\d[^-]*|BF16|F16)$/i, '')
}

function ModelFacts({ llm }: { llm: LlmStatus | null }) {
  if (!llm?.connected) {
    return <div className="notice warn">llama-server is not connected. Enter your paths below and start it, or launch it yourself in a terminal.</div>
  }
  return (
    <>
      <dl className="kv">
        <dt>Model</dt><dd>{llm.model_name}</dd>
        <dt>Endpoint</dt><dd className="mono">{llm.endpoint}</dd>
        <dt>Active context</dt><dd>{formatTokens(llm.context_size)} tokens</dd>
        {llm.train_context_size ? <><dt>Trained context</dt><dd>{formatTokens(llm.train_context_size)}</dd></> : null}
        <dt>Answer budget</dt><dd>{formatTokens(llm.max_output_tokens)} + {formatTokens(llm.safety_reserve)} reserve</dd>
        <dt>Images</dt><dd>{llm.supports_vision ? 'supported (projector loaded)' : 'not supported'}</dd>
        {llm.prompt_tokens_per_second ? <><dt>Reading speed</dt><dd>{llm.prompt_tokens_per_second} tok/s</dd></> : null}
        {llm.generated_tokens_per_second ? <><dt>Writing speed</dt><dd>{llm.generated_tokens_per_second} tok/s</dd></> : null}
      </dl>
      {llm.speed_warning && <div className="notice warn">{llm.speed_warning}</div>}
    </>
  )
}

function PrivacyDialog({ privacy, llm, onClose }: { privacy: PrivacyStatus | null; llm: LlmStatus | null; onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>Privacy</h3>
          <button className="btn small" onClick={onClose}>Close</button>
        </header>
        {privacy ? (
          <>
            <dl className="kv">
              <dt>Mode</dt><dd>{privacy.mode}</dd>
              <dt>Runtime</dt><dd>{privacy.llm_runtime}</dd>
              <dt>Endpoint</dt><dd className="mono">{privacy.llm_endpoint}</dd>
              <dt>Model</dt><dd>{llm?.model_name ?? '–'}</dd>
              <dt>Network needed</dt><dd>{privacy.network_needed}</dd>
              <dt>Cloud AI APIs</dt><dd>{privacy.cloud_ai_apis ? 'yes' : 'none'}</dd>
              <dt>Telemetry</dt><dd>{privacy.telemetry ? 'yes' : 'none'}</dd>
              <dt>Data folder</dt><dd className="mono">{privacy.data_dir}</dd>
            </dl>
            <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
              {privacy.notes.map((n, i) => (
                <li key={i} className={n.startsWith('WARNING') || n.includes('DISABLED') ? 'danger-text' : ''}>{n}</li>
              ))}
            </ul>
          </>
        ) : (
          <div className="notice error">Privacy status unavailable – the backend is not reachable.</div>
        )}
      </div>
    </div>
  )
}
