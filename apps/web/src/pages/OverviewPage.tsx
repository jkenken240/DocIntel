import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle2,
  FileClock,
  FileSearch,
  Files,
  MessageSquareText,
  Sparkles,
  Upload,
} from "lucide-react";

import { ErrorState, LoadingState } from "../components/Feedback";
import { StatusBadge } from "../components/StatusBadge";
import { describeError } from "../lib/api/client";
import { isDocumentTerminal, listAllDocuments } from "../lib/api/documents";
import { formatDate } from "../lib/format";
import { AppLink } from "../lib/router";

export function OverviewPage() {
  const documents = useQuery({
    queryKey: ["documents", "overview"],
    queryFn: ({ signal }) =>
      listAllDocuments({ sort: "created_at", order: "desc" }, signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (document) => !isDocumentTerminal(document.status),
      )
        ? 2_500
        : false,
  });

  if (documents.isPending) {
    return (
      <div className="page-frame">
        <LoadingState
          title="Opening DocIntel"
          message="Reading the current document lifecycle from the workspace."
        />
      </div>
    );
  }

  if (documents.isError) {
    const error = describeError(documents.error);
    return (
      <div className="page-frame">
        <ErrorState
          {...error}
          action={
            <button
              type="button"
              className="button button-secondary"
              onClick={() => void documents.refetch()}
            >
              Try again
            </button>
          }
        />
      </div>
    );
  }

  const items = documents.data.items;
  const ready = items.filter((document) => document.status === "ready").length;
  const processing = items.filter(
    (document) =>
      document.status === "queued" || document.status === "processing",
  ).length;
  const attention = items.filter(
    (document) => document.status === "failed",
  ).length;

  return (
    <div className="page-frame overview-page">
      <section className="overview-hero">
        <div className="hero-copy">
          <span className="eyebrow">
            <Sparkles size={14} aria-hidden="true" />
            Evidence, not guesswork
          </span>
          <h1>Turn dense PDFs into answers you can inspect.</h1>
          <p>
            Upload business documents, let DocIntel build page-correct evidence,
            then ask questions whose claims resolve to exact PDF sources.
          </p>
          <div className="button-row">
            <AppLink
              to="/documents?upload=1"
              className="button button-primary"
            >
              <Upload size={17} aria-hidden="true" />
              Upload documents
            </AppLink>
            <AppLink to="/ask" className="button button-secondary">
              <MessageSquareText size={17} aria-hidden="true" />
              Ask DocIntel
            </AppLink>
          </div>
        </div>
        <div className="evidence-orbit" aria-hidden="true">
          <span className="orbit-core">DI</span>
          <span className="orbit-node node-one" />
          <span className="orbit-node node-two" />
          <span className="orbit-node node-three" />
          <span className="orbit-line line-one" />
          <span className="orbit-line line-two" />
          <span className="orbit-caption caption-source">PDF source</span>
          <span className="orbit-caption caption-claim">Verified claim</span>
          <span className="orbit-caption caption-evidence">Exact evidence</span>
        </div>
      </section>

      <section className="metric-grid" aria-label="Workspace document counts">
        <article className="metric-card">
          <span className="metric-icon cyan">
            <Files size={20} aria-hidden="true" />
          </span>
          <div>
            <strong>{items.length}</strong>
            <span>Total documents</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon green">
            <CheckCircle2 size={20} aria-hidden="true" />
          </span>
          <div>
            <strong>{ready}</strong>
            <span>Ready for questions</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon violet">
            <FileClock size={20} aria-hidden="true" />
          </span>
          <div>
            <strong>{processing}</strong>
            <span>Still processing</span>
          </div>
        </article>
        <article className="metric-card">
          <span className="metric-icon amber">
            <FileSearch size={20} aria-hidden="true" />
          </span>
          <div>
            <strong>{attention}</strong>
            <span>Need attention</span>
          </div>
        </article>
      </section>

      <div className="overview-grid">
        <section
          className="surface-panel recent-panel"
          aria-labelledby="recent-title"
        >
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">Workspace activity</span>
              <h2 id="recent-title">Recent documents</h2>
            </div>
            <AppLink to="/documents" className="text-link">
              View library <ArrowRight size={15} aria-hidden="true" />
            </AppLink>
          </div>
          {items.length ? (
            <ul className="recent-list">
              {items.slice(0, 5).map((document) => (
                <li key={document.id}>
                  <AppLink to={`/documents/${document.id}`}>
                    <span className="recent-file-icon">
                      <Files size={17} aria-hidden="true" />
                    </span>
                    <span className="recent-file-copy">
                      <strong title={document.name}>{document.name}</strong>
                      <small>{formatDate(document.created_at)}</small>
                    </span>
                    <StatusBadge status={document.status} />
                  </AppLink>
                </li>
              ))}
            </ul>
          ) : (
            <div className="first-use">
              <span className="first-use-index">01</span>
              <div>
                <h3>Start with a PDF</h3>
                <p>
                  Upload a fictional or business PDF. DocIntel will validate,
                  extract, structure, and prepare it for grounded questions.
                </p>
                <AppLink to="/documents?upload=1" className="text-link">
                  Open secure upload <ArrowRight size={15} aria-hidden="true" />
                </AppLink>
              </div>
            </div>
          )}
        </section>

        <section
          className="surface-panel workflow-panel"
          aria-labelledby="workflow-title"
        >
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">How it works</span>
              <h2 id="workflow-title">A visible chain of evidence</h2>
            </div>
          </div>
          <ol className="workflow-steps">
            <li>
              <span>01</span>
              <div>
                <strong>Documents become evidence</strong>
                <p>Page-correct text and vectors are built deterministically.</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>Questions retrieve sources</strong>
                <p>Only compatible READY documents can support an answer.</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>Every claim stays inspectable</strong>
                <p>Exact excerpts remain connected to their original PDF page.</p>
              </div>
            </li>
          </ol>
        </section>
      </div>
    </div>
  );
}
