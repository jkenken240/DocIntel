import type {
  DocumentProgress,
  DocumentStage,
  DocumentStatus,
} from "./api/contracts";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${unit}`;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Unknown date";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function statusLabel(status: DocumentStatus): string {
  const labels: Record<DocumentStatus, string> = {
    queued: "Queued",
    processing: "Processing",
    ready: "Ready",
    failed: "Needs attention",
    deleting: "Deleting",
  };
  return labels[status];
}

export function stageLabel(stage: DocumentStage): string {
  const labels: Record<DocumentStage, string> = {
    queued: "Waiting for a worker",
    validating: "Validating PDF",
    extracting: "Extracting pages",
    chunking: "Structuring evidence",
    embedding: "Building search vectors",
    deleting: "Removing document",
  };
  return labels[stage];
}

export function progressLabel(progress: DocumentProgress): string {
  if (progress.total === null || progress.unit === null) {
    return progress.completed > 0 ? `${progress.completed} complete` : "Starting";
  }
  return `${progress.completed} of ${progress.total} ${progress.unit}`;
}

export function progressPercent(progress: DocumentProgress): number | null {
  if (progress.total === null || progress.total <= 0) return null;
  return Math.max(
    0,
    Math.min(100, Math.round((progress.completed / progress.total) * 100)),
  );
}

export function reasonLabel(code: string | null): string {
  const reasons: Record<string, string> = {
    NO_COMPATIBLE_EMBEDDING_SPACE:
      "No READY document currently matches the active intelligence configuration.",
    INSUFFICIENT_RETRIEVAL_SCORE:
      "The available documents did not contain sufficiently relevant evidence.",
    EVIDENCE_DOES_NOT_ANSWER:
      "The retrieved evidence did not directly answer this question.",
    UNSUPPORTED_CLAIM:
      "A proposed claim could not be verified against its cited evidence.",
    CONTRADICTORY_EVIDENCE:
      "The available evidence conflicted and could not support a safe answer.",
    SOURCE_CHANGED:
      "A source changed or was deleted before the answer could be finalized.",
    QUESTION_EMBEDDING_FAILED:
      "The question could not be compared with the active document evidence.",
    ANSWER_PROVIDER_INVALID:
      "A grounded answer could not be validated.",
    CITATION_VALIDATION_FAILED:
      "The proposed citations did not reproduce the stored source text exactly.",
    CLAIM_VERIFICATION_FAILED:
      "Claim support could not be verified safely.",
  };
  return code
    ? (reasons[code] ??
        "The available evidence did not meet DocIntel’s grounding requirements.")
    : "The available evidence did not meet DocIntel’s grounding requirements.";
}
