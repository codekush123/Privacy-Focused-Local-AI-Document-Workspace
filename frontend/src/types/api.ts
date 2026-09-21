export type SourceType = 'text' | 'txt' | 'md' | 'html' | 'url' | 'csv' | 'docx' | 'pdf' | 'xlsx' | 'pptx'

export interface DocumentSummary {
  id: string
  display_name: string
  original_filename: string
  source_type: SourceType
  status: 'ready' | 'error'
  error: string | null
  size_bytes: number
  character_count: number
  token_count: number | null
  section_count: number
  imported_at: string
  metadata: Record<string, unknown>
}

export interface LlmStatus {
  connected: boolean
  endpoint: string
  model_name: string | null
  model_path: string | null
  context_size: number | null
  train_context_size: number | null
  max_output_tokens: number
  safety_reserve: number
  allowed_prompt_tokens: number | null
  total_slots: number | null
  build_info: string | null
  error: string | null
  ai_requests_allowed: boolean
}

export interface PrivacyStatus {
  mode: string
  local_only: boolean
  llm_runtime: string
  llm_endpoint: string
  llm_endpoint_is_local: boolean
  ai_requests_allowed: boolean
  cloud_ai_apis: boolean
  analytics: boolean
  telemetry: boolean
  documents_leave_machine: boolean
  network_needed: string
  data_dir: string
  notes: string[]
}

export interface ContextCheck {
  fits: boolean
  prompt_tokens: number
  context_size: number
  max_output_tokens: number
  safety_reserve: number
  allowed_prompt_tokens: number
  model_name: string | null
  message: string
  suggestions: string[]
  strategy?: string
  document_count?: number
  sources?: string[]
  source_map?: SourceMapEntry[]
}

export interface ExportInfo {
  id: string
  filename: string
  kind: 'docx' | 'xlsx' | 'pptx' | 'csv' | 'md' | 'txt' | 'pdf' | 'tex'
  size_bytes: number
  created_at: string
  sources: string[]
  prompt: string
  download_url: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  context?: ContextCheck
  error?: string
  streaming?: boolean
  exportInfo?: ExportInfo
  sourceMap?: SourceMapEntry[]
  citations?: Citation[]
  citationStats?: CitationStats
  verification?: VerificationResult
  verifying?: boolean
}

export interface ApiError {
  error: string
  suggestions?: string[]
  context?: ContextCheck
  log_tail?: string[]
}

export type TextExportKind = 'md' | 'txt' | 'docx' | 'pdf' | 'tex'

export interface LauncherSettings {
  server_path: string
  model_path: string
  context_size: number
  threads: number
  gpu_layers: number
  extra_args: string
  reasoning_budget_off: boolean
}

export interface LauncherStatus {
  settings: LauncherSettings
  running: boolean
  managed: boolean
  pid: number | null
  started_at: number | null
  host: string
  port: number
  log_tail: string[]
  last_error: string | null
  settings_file: string
}

// ---------------------------------------------------------------- features
export interface SourceMapEntry { index: number; id: string; name: string; locators: string[] }

export interface Citation {
  marker: string
  source_index: number
  locator: string
  document_id: string | null
  document_name: string | null
  section_id: string | null
  resolved_locator: string | null
  found: boolean
}

export interface CitationStats { total: number; resolved: number; unresolved: string[] }

export interface DocSection { section_id: string; title: string; locator: string; markdown: string }

export type Verdict = 'supported' | 'partially_supported' | 'unsupported' | 'contradicted'
export interface Claim { claim: string; verdict: Verdict; evidence: string; source: string; note: string }
export interface VerificationResult {
  claims: Claim[]
  overall: string
  counts: Record<Verdict, number>
  grounding_score: number
  citations: Citation[]
}

export type QuestionType = 'multiple_choice' | 'true_false' | 'short_answer'
export interface QuizQuestion {
  type: QuestionType
  question: string
  options: string[]
  answer: string
  explanation: string
  source: string
  difficulty: 'easy' | 'medium' | 'hard'
}
export interface QuizSpec { title: string; questions: QuizQuestion[] }
export interface GradeResult { correct: boolean; score: number; feedback: string; graded_by: 'rules' | 'ai' }
export interface AnswerRecord {
  question: string
  type: string
  user_answer: string
  correct_answer: string
  correct: boolean
  score: number
  feedback: string
  source: string
}

export interface QueryPlan {
  computed: { name: string; expression: string }[]
  filters: { column: string; op: string; value: string }[]
  group_by: string
  aggregates: { column: string; func: string; alias: string }[]
  select: string[]
  sort: { column: string; descending: boolean }[]
  limit: number
  chart: { type: 'none' | 'bar' | 'line'; x: string; y: string }
  explanation: string
}
export interface QueryResult {
  columns: string[]
  rows: (string | number | null)[][]
  row_count: number
  total_rows: number
  plan: QueryPlan
  table_name: string
  sheets: string[]
}
export interface DataInfo { name: string; columns: string[]; row_count: number; sheets: string[]; preview: (string | number | null)[][] }

export type PiiCategory =
  | 'person' | 'email' | 'phone' | 'address' | 'organization' | 'id_number' | 'iban' | 'credit_card' | 'date_of_birth' | 'ip_address' | 'other'
export interface Finding {
  text: string
  category: PiiCategory
  count: number
  detected_by: 'pattern' | 'ai'
  reason: string
  context: string
}
export interface ScanResult { document_id: string; document_name: string; findings: Finding[]; ai_used: boolean; ai_error: string | null }
export interface RedactResult {
  replacements: Record<string, string>
  preview: string
  characters: number
  document?: { id: string; display_name: string }
  export?: ExportInfo
}
