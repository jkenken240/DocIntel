import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Eye,
  FileText,
  Filter,
  MessageSquareText,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";

import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  SuccessNotice,
} from "../components/Feedback";
import { LifecycleProgress, StatusBadge } from "../components/StatusBadge";
import { UploadQueue } from "../components/UploadQueue";
import { ApiProblem, describeError } from "../lib/api/client";
import type {
  DocumentStatus,
  DocumentSummary,
} from "../lib/api/contracts";
import {
  deleteDocument,
  getDocument,
  isDocumentTerminal,
  listAllDocuments,
  retryDocument,
  type DocumentSort,
  type SortOrder,
} from "../lib/api/documents";
import { formatBytes, formatDate } from "../lib/format";
import { AppLink, useRouter } from "../lib/router";

const statusOptions: Array<{ value: "" | DocumentStatus; label: string }> = [
  { value: "", label: "All statuses" },
  { value: "ready", label: "Ready" },
  { value: "processing", label: "Processing" },
  { value: "queued", label: "Queued" },
  { value: "failed", label: "Needs attention" },
  { value: "deleting", label: "Deleting" },
];

function selectedFromSearch(search: URLSearchParams): Set<string> {
  return new Set(
    (search.get("selected") ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
  );
}

function DocumentActions({
  document,
  onDelete,
}: {
  document: DocumentSummary;
  onDelete: (document: DocumentSummary) => void;
}) {
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["document", document.id],
    queryFn: ({ signal }) => getDocument(document.id, signal),
    enabled: document.status === "failed",
    retry: false,
  });
  const retry = useMutation({
    mutationFn: () => retryDocument(document.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      await queryClient.invalidateQueries({
        queryKey: ["document", document.id],
      });
    },
  });
  const retryable =
    document.status === "failed" && detail.data?.error?.retryable === true;

  return (
    <div className="document-actions">
      {retryable ? (
        <button
          type="button"
          className="icon-button"
          aria-label={`Retry processing ${document.name}`}
          disabled={retry.isPending}
          onClick={() => retry.mutate()}
        >
          <RefreshCw
            size={17}
            className={retry.isPending ? "spin" : undefined}
            aria-hidden="true"
          />
        </button>
      ) : null}
      <AppLink
        to={`/documents/${document.id}`}
        className="icon-button"
        aria-label={`Open ${document.name}`}
      >
        <Eye size={17} aria-hidden="true" />
      </AppLink>
      <button
        type="button"
        className="icon-button danger-ghost"
        aria-label={`Delete ${document.name}`}
        disabled={document.status === "deleting"}
        onClick={() => onDelete(document)}
      >
        <Trash2 size={17} aria-hidden="true" />
      </button>
    </div>
  );
}

export function DocumentsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [status, setStatus] = useState<"" | DocumentStatus>("");
  const [sortValue, setSortValue] = useState("created_at:desc");
  const [selected, setSelected] = useState<Set<string>>(() =>
    selectedFromSearch(router.search),
  );
  const [deleteTarget, setDeleteTarget] = useState<DocumentSummary | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sort, order] = sortValue.split(":") as [DocumentSort, SortOrder];

  const documents = useQuery({
    queryKey: ["documents", "library", deferredSearch, status, sort, order],
    queryFn: ({ signal }) =>
      listAllDocuments(
        {
          search: deferredSearch,
          statuses: status ? [status] : undefined,
          sort,
          order,
        },
        signal,
      ),
    retry: false,
    placeholderData: (previous) => previous,
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (document) => !isDocumentTerminal(document.status),
      )
        ? 2_000
        : false,
  });

  const deletion = useMutation({
    mutationFn: (documentId: string) => deleteDocument(documentId),
    onSuccess: async (response) => {
      setNotice(`Deletion accepted for ${response.document.name}.`);
      setSelected((current) => {
        const next = new Set(current);
        next.delete(response.document.id);
        return next;
      });
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: async (error) => {
      if (error instanceof ApiProblem && error.status === 404) {
        setNotice("The document had already been removed.");
        setDeleteTarget(null);
        await queryClient.invalidateQueries({ queryKey: ["documents"] });
      }
    },
  });

  const items = useMemo(() => documents.data?.items ?? [], [documents.data]);
  const readyIds = useMemo(
    () =>
      new Set(
        items
          .filter((item) => item.status === "ready")
          .map((item) => item.id),
      ),
    [items],
  );

  const effectiveSelected = useMemo(
    () => new Set([...selected].filter((id) => readyIds.has(id))),
    [readyIds, selected],
  );

  function toggleSelection(documentId: string) {
    setSelected((current) => {
      const next = new Set([...current].filter((id) => readyIds.has(id)));
      if (next.has(documentId)) next.delete(documentId);
      else next.add(documentId);
      return next;
    });
  }

  const selectionQuery = [...effectiveSelected].join(",");
  const deletionError = deletion.isError ? describeError(deletion.error) : null;

  return (
    <div className="page-frame documents-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Source operations</span>
          <h1>Document library</h1>
          <p>
            Upload, inspect, and select only verified READY documents for
            grounded questions.
          </p>
        </div>
        <AppLink
          to={`/ask${selectionQuery ? `?documents=${selectionQuery}` : ""}`}
          className={`button button-primary ${effectiveSelected.size ? "" : "button-muted"}`}
        >
          <MessageSquareText size={17} aria-hidden="true" />
          Ask with {effectiveSelected.size || "all READY"}
        </AppLink>
      </header>

      <UploadQueue autoFocus={router.search.get("upload") === "1"} />

      <section className="library-panel" aria-labelledby="library-title">
        <div className="library-heading">
          <div>
            <span className="eyebrow">Protected sources</span>
            <h2 id="library-title">Workspace files</h2>
          </div>
          <span className="library-count">
            {items.length} {items.length === 1 ? "document" : "documents"}
          </span>
        </div>

        <div className="library-toolbar">
          <div className="search-field">
            <Search size={17} aria-hidden="true" />
            <label className="visually-hidden" htmlFor="document-search">
              Search documents
            </label>
            <input
              id="document-search"
              type="search"
              value={search}
              placeholder="Search by filename"
              onChange={(event) => setSearch(event.target.value)}
            />
            {search ? (
              <button
                type="button"
                className="field-clear"
                aria-label="Clear document search"
                onClick={() => setSearch("")}
              >
                <X size={15} aria-hidden="true" />
              </button>
            ) : null}
          </div>
          <label className="select-field">
            <Filter size={16} aria-hidden="true" />
            <span className="visually-hidden">Filter by status</span>
            <select
              value={status}
              onChange={(event) =>
                setStatus(event.target.value as "" | DocumentStatus)
              }
            >
              {statusOptions.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <ChevronDown size={15} aria-hidden="true" />
          </label>
          <label className="select-field">
            <span className="visually-hidden">Sort documents</span>
            <select
              value={sortValue}
              onChange={(event) => setSortValue(event.target.value)}
            >
              <option value="created_at:desc">Newest first</option>
              <option value="created_at:asc">Oldest first</option>
              <option value="name:asc">Name A–Z</option>
              <option value="name:desc">Name Z–A</option>
              <option value="size:desc">Largest first</option>
              <option value="size:asc">Smallest first</option>
            </select>
            <ChevronDown size={15} aria-hidden="true" />
          </label>
        </div>

        {notice ? (
          <SuccessNotice>
            {notice}
            <button
              type="button"
              className="notice-dismiss"
              aria-label="Dismiss notification"
              onClick={() => setNotice(null)}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </SuccessNotice>
        ) : null}

        {deletionError ? (
          <ErrorState
            {...deletionError}
            action={
              <button
                type="button"
                className="button button-secondary"
                onClick={() => deletion.reset()}
              >
                Dismiss
              </button>
            }
          />
        ) : null}

        {documents.isPending ? (
          <LoadingState
            title="Loading document library"
            message="Reading current lifecycle states."
          />
        ) : documents.isError ? (
          <ErrorState
            {...describeError(documents.error)}
            action={
              <button
                type="button"
                className="button button-secondary"
                onClick={() => void documents.refetch()}
              >
                Retry library
              </button>
            }
          />
        ) : items.length === 0 ? (
          <EmptyState
            title={
              search || status
                ? "No documents match this view"
                : "No documents yet"
            }
            message={
              search || status
                ? "Clear the search or choose another lifecycle status."
                : "Use the secure upload queue above to add your first PDF."
            }
            action={
              search || status ? (
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => {
                    setSearch("");
                    setStatus("");
                  }}
                >
                  Clear filters
                </button>
              ) : undefined
            }
          />
        ) : (
          <div
            className={`document-list ${documents.isFetching ? "is-stale" : ""}`}
            role="list"
            aria-busy={documents.isFetching}
          >
            <div className="document-list-head" aria-hidden="true">
              <span>Source</span>
              <span>Lifecycle</span>
              <span>Added</span>
              <span>Actions</span>
            </div>
            {items.map((document) => {
              const canSelect = document.status === "ready";
              return (
                <article
                  key={document.id}
                  className={`document-row ${effectiveSelected.has(document.id) ? "selected" : ""}`}
                  role="listitem"
                >
                  <div className="document-identity">
                    <label
                      className={`source-check ${canSelect ? "" : "disabled"}`}
                      title={
                        canSelect
                          ? "Select as a question source"
                          : "Only READY documents can be selected"
                      }
                    >
                      <input
                        type="checkbox"
                        checked={effectiveSelected.has(document.id)}
                        disabled={!canSelect}
                        onChange={() => toggleSelection(document.id)}
                        aria-label={`Select ${document.name} as a question source`}
                      />
                      <span aria-hidden="true">
                        {effectiveSelected.has(document.id) ? (
                          <Check size={13} />
                        ) : null}
                      </span>
                    </label>
                    <span className="document-symbol">
                      <FileText size={19} aria-hidden="true" />
                    </span>
                    <span className="document-name">
                      <AppLink
                        to={`/documents/${document.id}`}
                        title={document.name}
                      >
                        {document.name}
                      </AppLink>
                      <small>{formatBytes(document.byte_size)} · PDF</small>
                    </span>
                  </div>
                  <div className="document-lifecycle">
                    <StatusBadge status={document.status} />
                    <LifecycleProgress
                      status={document.status}
                      stage={document.stage}
                      progress={document.progress}
                      compact
                    />
                  </div>
                  <time dateTime={document.created_at}>
                    {formatDate(document.created_at)}
                  </time>
                  <DocumentActions
                    document={document}
                    onDelete={setDeleteTarget}
                  />
                </article>
              );
            })}
          </div>
        )}

        {effectiveSelected.size ? (
          <div className="selection-dock" role="status">
            <span>
              <strong>{effectiveSelected.size}</strong> READY{" "}
              {effectiveSelected.size === 1 ? "source" : "sources"} selected
            </span>
            <button
              type="button"
              className="text-button"
              onClick={() => setSelected(new Set())}
            >
              Clear
            </button>
            <AppLink
              to={`/ask?documents=${selectionQuery}`}
              className="button button-primary button-small"
            >
              Ask with selection <ArrowRight size={15} aria-hidden="true" />
            </AppLink>
          </div>
        ) : null}
      </section>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Delete ${deleteTarget?.name ?? "document"}?`}
        description="The protected PDF, derived evidence, and any grounded answers that depend on this document will be removed. This cannot be undone."
        confirmLabel="Delete document"
        busy={deletion.isPending}
        onCancel={() => {
          if (!deletion.isPending) setDeleteTarget(null);
        }}
        onConfirm={() => {
          if (deleteTarget) deletion.mutate(deleteTarget.id);
        }}
      />
    </div>
  );
}
