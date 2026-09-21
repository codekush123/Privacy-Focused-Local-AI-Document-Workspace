import type {
  AnswerRecord,
  ApiError,
  Citation,
  CitationStats,
  ContextCheck,
  DataInfo,
  DocSection,
  DocumentSummary,
  ExportInfo,
  GradeResult,
  QueryResult,
  QuestionType,
  QuizQuestion,
  QuizSpec,
  RedactResult,
  ScanResult,
  VerificationResult,
  LauncherSettings,
  LauncherStatus,
  LlmStatus,
  PrivacyStatus,
  TextExportKind,
} from '../types/api'

export class RequestError extends Error {
  status: number
  suggestions: string[]
  context?: ContextCheck
  logTail: string[]
  constructor(status: number, body: ApiError) {
    super(body.error || `Request failed (${status})`)
    this.status = status
    this.suggestions = body.suggestions ?? []
    this.context = body.context
    this.logTail = body.log_tail ?? []
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch {
    throw new RequestError(0, { error: 'The backend is not reachable. Start it with scripts/start_backend.' })
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }
  if (!res.ok) {
    const err = (body as ApiError) ?? { error: text || `Request failed (${res.status})` }
    throw new RequestError(res.status, err)
  }
  return body as T
}

const json = (data: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
})

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  llmStatus: () => request<LlmStatus>('/api/llm/status'),
  privacy: () => request<PrivacyStatus>('/api/privacy'),

  listDocuments: () => request<DocumentSummary[]>('/api/documents'),
  supported: () => request<{ extensions: string[]; max_upload_bytes: number }>('/api/documents/supported'),
  upload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<DocumentSummary>('/api/documents/upload', { method: 'POST', body: fd })
  },
  importText: (text: string, name?: string) => request<DocumentSummary>('/api/documents/text', json({ text, name })),
  importUrl: (url: string) => request<DocumentSummary>('/api/documents/url', json({ url })),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: 'DELETE' }),
  clearDocuments: () => request<{ deleted: number }>('/api/documents', { method: 'DELETE' }),
  documentPreview: (id: string, chars = 4000) =>
    request<{ full_markdown: string }>(`/api/documents/${id}?preview_chars=${chars}`),

  quickActions: () => request<Record<string, string>>('/api/chat/quick-actions'),
  translatePrompt: (language: string) => request<{ prompt: string }>(`/api/chat/translate-prompt?language=${encodeURIComponent(language)}`),
  documentSections: (id: string) => request<DocSection[]>(`/api/documents/${id}/sections`),

  verify: (answer: string, document_ids: string[]) => request<VerificationResult>('/api/verify', json({ answer, document_ids })),

  studyQuiz: (document_ids: string[], count: number, types: QuestionType[], difficulty: string) =>
    request<QuizSpec>('/api/study/quiz', json({ document_ids, count, types, difficulty })),
  studyGrade: (question: QuizQuestion, user_answer: string) => request<GradeResult>('/api/study/grade', json({ question, user_answer })),
  studyReport: (title: string, records: AnswerRecord[], document_ids: string[], kind: 'xlsx' | 'docx') =>
    request<ExportInfo>('/api/study/report', json({ title, records, document_ids, kind })),

  dataInfo: (id: string, sheet?: string) => request<DataInfo>(`/api/data/${id}/info${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ''}`),
  dataQuery: (document_id: string, question: string, sheet?: string) => request<QueryResult>('/api/data/query', json({ document_id, question, sheet })),
  dataExport: (title: string, columns: string[], rows: unknown[][], document_id: string, note: string) =>
    request<ExportInfo>('/api/data/export', json({ title, columns, rows, document_id, note })),

  privacyScan: (document_id: string, use_ai: boolean) => request<ScanResult>('/api/privacy/scan', json({ document_id, use_ai })),
  privacyRedact: (document_id: string, items: { text: string; category: string; replacement: string }[], exportKind: string, add_to_library: boolean) =>
    request<RedactResult>('/api/privacy/redact', json({ document_id, items, export: exportKind, add_to_library })),
  contextCheck: (prompt: string, document_ids: string[]) =>
    request<ContextCheck>('/api/context/check', json({ prompt, document_ids })),

  generate: (kind: 'docx' | 'xlsx' | 'pptx' | 'csv', prompt: string, document_ids: string[]) =>
    request<ExportInfo>(`/api/generate/${kind}`, json({ prompt, document_ids })),
  saveText: (text: string, kind: TextExportKind, prompt: string, document_ids: string[], title?: string) =>
    request<ExportInfo>('/api/exports/save-text', json({ text, kind, prompt, document_ids, title })),
  listExports: () => request<ExportInfo[]>('/api/exports'),

  launcherStatus: () => request<LauncherStatus>('/api/llm/launcher'),
  launcherSave: (s: LauncherSettings) =>
    request<LauncherStatus>('/api/llm/launcher/settings', { ...json(s), method: 'PUT' }),
  launcherValidate: (s: LauncherSettings) =>
    request<{ ok: boolean; problems: string[]; command: string[] }>('/api/llm/launcher/validate', json(s)),
  launcherStart: (s: LauncherSettings) => request<LauncherStatus>('/api/llm/launcher/start', json(s)),
  launcherStop: () => request<LauncherStatus>('/api/llm/launcher/stop', { method: 'POST' }),
  deleteExport: (id: string) => request<void>(`/api/exports/${id}`, { method: 'DELETE' }),
  clearExports: () => request<{ deleted: number }>('/api/exports', { method: 'DELETE' }),
}

export interface StreamDone { usage: Record<string, unknown>; citations?: Citation[]; citation_stats?: CitationStats; elapsed_seconds?: number }
export interface StreamHandlers {
  onContext: (ctx: ContextCheck) => void
  onDelta: (text: string) => void
  onDone: (done: StreamDone) => void
  onError: (message: string) => void
}

/** Streams a chat answer over Server-Sent Events. Throws RequestError before streaming starts. */
export async function streamChat(
  prompt: string,
  document_ids: string[],
  history: { role: 'user' | 'assistant'; content: string }[],
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch('/api/chat', { ...json({ prompt, document_ids, history, stream: true }), signal })
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    throw new RequestError(0, { error: 'The backend is not reachable. Start it with scripts/start_backend.' })
  }
  if (!res.ok) {
    let body: ApiError = { error: `Request failed (${res.status})` }
    try {
      body = await res.json()
    } catch {
      /* ignore */
    }
    throw new RequestError(res.status, body)
  }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let event = 'message'
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, idx).replace(/\r$/, '')
        buffer = buffer.slice(idx + 1)
        if (line.startsWith('event:')) {
          event = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const data = JSON.parse(line.slice(5))
          if (event === 'context') handlers.onContext(data)
          else if (event === 'delta') handlers.onDelta(data.content)
          else if (event === 'done') handlers.onDone(data)
          else if (event === 'error') handlers.onError(data.error)
        }
      }
    }
  } catch (e) {
    if ((e as Error).name !== 'AbortError') handlers.onError('The connection to the backend was interrupted.')
  }
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export function formatTokens(n: number | null | undefined): string {
  return n == null ? '–' : n.toLocaleString('en-US')
}
