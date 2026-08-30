export type DocType = "PUBEX" | "FS_QUARTERLY" | "FS_ANNUAL" | "ANNUAL_REPORT";
export type Language = "id" | "en" | "mixed";

export interface UploadRequest {
  ticker: string;
  doc_type: DocType;
  fiscal_period: string;
  language: Language;
  file: File;
  xbrl_file?: File | null;
}

export interface UploadResponse {
  document_id: string;
  status: string;
  deduplicated: boolean;
}

export interface ProposedMetadata {
  ticker: string | null;
  fiscal_period: string | null;
  doc_type: DocType | null;
  language: Language;
  confidence: Partial<Record<"ticker" | "fiscal_period" | "doc_type", number>>;
  evidence_snippet: string | null;
  source: "regex" | "llm" | "mixed" | "none";
}

export interface InspectResponse {
  document_id: string;
  proposed: ProposedMetadata;
  deduplicated: boolean;
  existing_status?: string | null;
}

export interface ApproveRequest {
  ticker: string;
  doc_type: DocType;
  fiscal_period: string;
  language: Language;
}

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface ChatCitation {
  fact_id?: number | null;
  chunk_id?: string | null;
  document_id: string;
  ticker: string;
  fiscal_period: string;
  page?: number | null;
  bbox?: BBox | null;
  snippet?: string | null;
  citation_tag?: string | null;
}

export interface CitationDetail {
  citation: string;
  ticker: string;
  fiscal_period: string;
  page: number;
  bbox?: number[] | null;
  document?: Record<string, any> | null;
  fact?: Record<string, any> | null;
  chunk?: Record<string, any> | null;
  image_base64?: string | null;
  image_error?: string | null;
}

export interface ChatRequest {
  session_id?: string;
  message: string;
  focus_ticker?: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  citations: ChatCitation[];
  latency_ms?: number | null;
  token_usage?: Record<string, any> | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  citations?: ChatCitation[];
  retrieval_manifest?: Record<string, any> | null;
  token_usage?: Record<string, any> | null;
  latency_ms?: number | null;
}

export interface SessionSummary {
  id: string;
  title: string;
  last_activity_at: string;
  created_at: string;
  turn_count: number;
  last_message_preview: string;
  sticky_state: Record<string, any>;
}

export interface SessionTurn {
  id: number;
  role: "user" | "assistant";
  content: string;
  retrieval_manifest?: Record<string, any> | null;
  token_usage?: Record<string, any> | null;
  latency_ms?: number | null;
  ts: string;
}

export interface AuthResponse {
  token: string;
  user_id: string;
  email: string;
  expires_at: string;
}
