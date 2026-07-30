export type ComponentStatus = "ready" | "not_ready";

export interface ComponentCheck {
  status: ComponentStatus;
  detail: string;
}

export interface ReadinessResponse {
  status: ComponentStatus;
  checks: Record<string, ComponentCheck>;
}

export type DocumentStatus =
  | "queued"
  | "processing"
  | "ready"
  | "failed"
  | "deleting";

export type DocumentStage =
  | "queued"
  | "validating"
  | "extracting"
  | "chunking"
  | "embedding"
  | "deleting";

export type ProgressUnit = "bytes" | "pages" | "chunks";

export interface DocumentProgress {
  completed: number;
  total: number | null;
  unit: ProgressUnit | null;
}

export interface DocumentError {
  code: string;
  message: string;
  retryable: boolean | null;
}

export interface DocumentSummary {
  id: string;
  name: string;
  media_type: string;
  byte_size: number;
  status: DocumentStatus;
  stage: DocumentStage;
  progress: DocumentProgress;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  sha256: string;
  page_count: number;
  text_page_count: number;
  chunk_count: number;
  processing_revision: number;
  processing_version: string;
  pdf_metadata: Record<string, string>;
  stage_started_at: string | null;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  error: DocumentError | null;
}

export interface DocumentEnvelope {
  document: DocumentDetail;
}

export interface DocumentListResponse {
  items: DocumentSummary[];
  next_cursor: string | null;
}

export interface DocumentStatusResponse {
  id: string;
  status: DocumentStatus;
  stage: DocumentStage;
  progress: DocumentProgress;
  error: DocumentError | null;
  updated_at: string;
}

export interface ProviderSnapshot {
  provider: string;
  model: string;
  configuration_hash: string;
}

export interface EmbeddingSpaceSnapshot extends ProviderSnapshot {
  id: string | null;
  dimensions: number;
  distance_metric: string;
}

export interface EvidenceRecord {
  id: string;
  document_id: string;
  filename: string;
  processing_revision: number;
  page_id: string;
  page_number: number;
  chunk_id: string;
  chunk_ordinal: number;
  char_start: number;
  char_end: number;
  excerpt: string;
  text_sha256: string;
  retrieval_score: number;
  retrieval_rank: number;
}

export interface CitationRecord {
  id: string;
  evidence_id: string;
  document_id: string;
  filename: string;
  page_number: number;
  chunk_id: string;
  char_start: number;
  char_end: number;
  excerpt: string;
  text_sha256: string;
  retrieval_score: number;
  retrieval_rank: number;
}

export interface ClaimRecord {
  id: string;
  ordinal: number;
  char_start: number;
  char_end: number;
  text: string;
  supported: boolean;
  verification_reason_code: string;
  citations: CitationRecord[];
}

export type QuestionStatus = "processing" | "answered" | "insufficient_evidence";

export interface QuestionResponse {
  id: string;
  question: string;
  selected_document_ids: string[];
  status: QuestionStatus;
  insufficient_reason_code: string | null;
  answer_id: string | null;
  answer_text: string | null;
  claims: ClaimRecord[];
  evidence: EvidenceRecord[];
  retrieval_configuration: Record<string, number>;
  retrieval_configuration_hash: string;
  embedding_space: EmbeddingSpaceSnapshot;
  answer_provider: ProviderSnapshot;
  verifier_provider: ProviderSnapshot;
  created_at: string;
}

export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  trace_id?: string;
}
