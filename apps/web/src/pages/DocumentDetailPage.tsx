import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarClock,
  FileCheck2,
  FileText,
  Hash,
  Layers3,
  MessageSquareText,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  SuccessNotice,
} from "../components/Feedback";
import { PdfViewer } from "../components/PdfViewer";
import { LifecycleProgress, StatusBadge } from "../components/StatusBadge";
import { ApiProblem, describeError } from "../lib/api/client";
import {
  deleteDocument,
  getDocument,
  isDocumentTerminal,
  retryDocument,
} from "../lib/api/documents";
import { formatBytes, formatDate } from "../lib/format";
import { AppLink } from "../lib/router";

export function DocumentDetailPage({ documentId }: { documentId: string }) {
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deletionAccepted, setDeletionAccepted] = useState(false);

  const document = useQuery({
    queryKey: ["document", documentId],
    queryFn: ({ signal }) => getDocument(documentId, signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data && !isDocumentTerminal(query.state.data.status)
        ? 1_500
        : false,
  });

  const retry = useMutation({
    mutationFn: () => retryDocument(documentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["document", documentId],
      });
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const deletion = useMutation({
    mutationFn: () => deleteDocument(documentId),
    onSuccess: async () => {
      setDeletionAccepted(true);
      setConfirmDelete(false);
      await queryClient.invalidateQueries({
        queryKey: ["document", documentId],
      });
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  if (document.isPending) {
    return (
      <div className="page-frame">
        <LoadingState
          title="Opening document"
          message="Reading protected source metadata."
        />
      </div>
    );
  }

  if (document.isError) {
    if (
      deletionAccepted &&
      document.error instanceof ApiProblem &&
      document.error.status === 404
    ) {
      return (
        <div className="page-frame">
          <EmptyState
            title="Deletion complete"
            message="The PDF and its document-owned evidence are no longer in the workspace."
            action={
              <AppLink to="/documents" className="button button-primary">
                Return to document library
              </AppLink>
            }
          />
        </div>
      );
    }
    return (
      <div className="page-frame">
        <ErrorState
          {...describeError(document.error)}
          action={
            <AppLink to="/documents" className="button button-secondary">
              Back to documents
            </AppLink>
          }
        />
      </div>
    );
  }

  const item = document.data;
  const actionError =
    retry.isError || deletion.isError
      ? describeError(retry.error ?? deletion.error)
      : null;

  return (
    <div className="page-frame document-detail-page">
      <AppLink to="/documents" className="back-link">
        <ArrowLeft size={16} aria-hidden="true" />
        Document library
      </AppLink>

      <header className="document-detail-header">
        <div className="detail-file-symbol">
          <FileText size={27} aria-hidden="true" />
        </div>
        <div className="detail-title">
          <span className="eyebrow">Protected PDF source</span>
          <h1>{item.name}</h1>
          <div className="detail-status-line">
            <StatusBadge status={item.status} />
            <span>{formatBytes(item.byte_size)}</span>
            <span>Added {formatDate(item.created_at)}</span>
          </div>
        </div>
        <div className="detail-actions">
          {item.status === "ready" ? (
            <AppLink
              to={`/ask?documents=${item.id}`}
              className="button button-primary"
            >
              <MessageSquareText size={17} aria-hidden="true" />
              Ask this document
            </AppLink>
          ) : null}
          {item.status === "failed" && item.error?.retryable ? (
            <button
              type="button"
              className="button button-secondary"
              disabled={retry.isPending}
              onClick={() => retry.mutate()}
            >
              <RefreshCw
                size={17}
                className={retry.isPending ? "spin" : undefined}
                aria-hidden="true"
              />
              Retry processing
            </button>
          ) : null}
          <button
            type="button"
            className="button button-danger-subtle"
            disabled={item.status === "deleting"}
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 size={17} aria-hidden="true" />
            Delete
          </button>
        </div>
      </header>

      {deletionAccepted ? (
        <SuccessNotice>
          Deletion was accepted. DocIntel is confirming the protected file is
          absent.
        </SuccessNotice>
      ) : null}
      {actionError ? <ErrorState {...actionError} /> : null}

      <section
        className="detail-lifecycle surface-panel"
        aria-labelledby="lifecycle-title"
      >
        <div className="section-heading compact">
          <div>
            <span className="eyebrow">Truthful lifecycle</span>
            <h2 id="lifecycle-title">Processing state</h2>
          </div>
          <StatusBadge status={item.status} />
        </div>
        <LifecycleProgress
          status={item.status}
          stage={item.stage}
          progress={item.progress}
        />
        {item.error ? (
          <div className="document-error" role="alert">
            <strong>{item.error.code.replaceAll("_", " ")}</strong>
            <span>{item.error.message}</span>
          </div>
        ) : null}
      </section>

      <section className="detail-metrics" aria-label="Document metadata">
        <article>
          <FileCheck2 size={18} aria-hidden="true" />
          <span>PDF pages</span>
          <strong>{item.page_count || "—"}</strong>
        </article>
        <article>
          <Layers3 size={18} aria-hidden="true" />
          <span>Evidence chunks</span>
          <strong>{item.chunk_count || "—"}</strong>
        </article>
        <article>
          <CalendarClock size={18} aria-hidden="true" />
          <span>Last updated</span>
          <strong>{formatDate(item.updated_at)}</strong>
        </article>
        <article>
          <Hash size={18} aria-hidden="true" />
          <span>Content fingerprint</span>
          <strong title={item.sha256}>{item.sha256.slice(0, 12)}…</strong>
        </article>
      </section>

      {item.status !== "deleting" ? (
        <PdfViewer documentId={item.id} filename={item.name} initialPage={1} />
      ) : (
        <LoadingState
          title="Removing protected source"
          message="The PDF viewer is unavailable while deletion is being confirmed."
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${item.name}?`}
        description="The protected PDF, derived evidence, and any grounded answers that depend on this document will be removed. This cannot be undone."
        confirmLabel="Delete document"
        busy={deletion.isPending}
        onCancel={() => {
          if (!deletion.isPending) setConfirmDelete(false);
        }}
        onConfirm={() => deletion.mutate()}
      />
    </div>
  );
}
