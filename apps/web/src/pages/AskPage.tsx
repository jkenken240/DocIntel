import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  FileCheck2,
  MessageSquareText,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { describeError } from "../lib/api/client";
import { listAllDocuments } from "../lib/api/documents";
import {
  askQuestion,
  QUESTION_MAX_CHARS,
  QUESTION_MAX_DOCUMENTS,
} from "../lib/api/questions";
import { formatDate } from "../lib/format";
import { AppLink, useRouter } from "../lib/router";

function initialSelection(search: URLSearchParams): string[] {
  return [
    ...new Set(
      (search.get("documents") ?? "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  ].slice(0, QUESTION_MAX_DOCUMENTS);
}

export function AskPage() {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const requestController = useRef<AbortController | null>(null);
  const [question, setQuestion] = useState("");
  const [sourceMode, setSourceMode] = useState<"all" | "selected">(
    router.search.get("documents") ? "selected" : "all",
  );
  const [selected, setSelected] = useState<string[]>(() =>
    initialSelection(router.search),
  );
  const [sourceSearch, setSourceSearch] = useState("");

  useEffect(
    () => () => {
      requestController.current?.abort();
    },
    [],
  );

  const documents = useQuery({
    queryKey: ["documents", "ready-sources"],
    queryFn: ({ signal }) =>
      listAllDocuments(
        { statuses: ["ready"], sort: "name", order: "asc" },
        signal,
      ),
    retry: false,
  });

  const readyDocuments = useMemo(
    () => documents.data?.items ?? [],
    [documents.data],
  );
  const validIds = useMemo(
    () => new Set(readyDocuments.map((document) => document.id)),
    [readyDocuments],
  );

  const validSelected = selected.filter((id) => validIds.has(id));

  const submission = useMutation({
    mutationFn: async () => {
      requestController.current?.abort();
      requestController.current = new AbortController();
      return askQuestion(
        question,
        sourceMode === "selected" ? validSelected : [],
        requestController.current.signal,
      );
    },
    onSuccess: (result) => router.navigate(`/questions/${result.id}`),
  });

  const filteredSources = readyDocuments.filter((document) =>
    document.name
      .toLocaleLowerCase()
      .includes(sourceSearch.toLocaleLowerCase()),
  );
  const remaining = QUESTION_MAX_CHARS - question.length;
  const trimmed = question.trim();
  const canSubmit =
    !submission.isPending &&
    trimmed.length > 0 &&
    question.length <= QUESTION_MAX_CHARS &&
    readyDocuments.length > 0 &&
    (sourceMode === "all" || validSelected.length > 0);

  function toggleSource(documentId: string) {
    setSelected((current) => {
      const currentValid = current.filter((id) => validIds.has(id));
      if (currentValid.includes(documentId)) {
        return currentValid.filter((id) => id !== documentId);
      }
      if (currentValid.length >= QUESTION_MAX_DOCUMENTS) return currentValid;
      return [...currentValid, documentId];
    });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (canSubmit) submission.mutate();
  }

  if (documents.isPending) {
    return (
      <div className="page-frame">
        <LoadingState
          title="Preparing question workspace"
          message="Finding READY documents that can support grounded answers."
        />
      </div>
    );
  }

  if (documents.isError) {
    return (
      <div className="page-frame">
        <ErrorState
          {...describeError(documents.error)}
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

  if (!readyDocuments.length) {
    return (
      <div className="page-frame">
        <EmptyState
          title="No READY documents yet"
          message="Upload a PDF and wait for deterministic processing to finish before asking a grounded question."
          action={
            <AppLink to="/documents?upload=1" className="button button-primary">
              Upload documents
            </AppLink>
          }
        />
      </div>
    );
  }

  const submissionError = submission.isError
    ? describeError(submission.error)
    : null;

  return (
    <div className="page-frame ask-page">
      <header className="ask-header">
        <span className="eyebrow">
          <Sparkles size={14} aria-hidden="true" />
          Grounded intelligence
        </span>
        <h1>Ask the evidence, not a chatbot.</h1>
        <p>
          DocIntel retrieves from READY sources, validates exact citations, and
          refuses when the evidence cannot support an answer.
        </p>
      </header>

      <form
        ref={formRef}
        className="question-layout"
        onSubmit={submit}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            formRef.current?.requestSubmit();
          }
        }}
      >
        <section className="question-composer" aria-labelledby="question-title">
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">Your question</span>
              <h2 id="question-title">What do you need to know?</h2>
            </div>
            <MessageSquareText size={22} aria-hidden="true" />
          </div>
          <label htmlFor="grounded-question" className="visually-hidden">
            Question for DocIntel
          </label>
          <textarea
            id="grounded-question"
            value={question}
            maxLength={QUESTION_MAX_CHARS}
            placeholder="For example: How long must audit records be retained, and do the sources agree?"
            onChange={(event) => setQuestion(event.target.value)}
            aria-describedby="question-guidance question-limit"
            autoFocus
          />
          <div className="composer-meta">
            <span id="question-guidance">
              Use Ctrl or ⌘ + Enter to submit
            </span>
            <span
              id="question-limit"
              className={remaining < 150 ? "limit-warning" : ""}
            >
              {remaining.toLocaleString()} characters remaining
            </span>
          </div>

          <div className="selected-source-strip" aria-live="polite">
            <ShieldCheck size={16} aria-hidden="true" />
            {sourceMode === "all" ? (
              <span>
                Searching all <strong>{readyDocuments.length}</strong> eligible
                READY documents
              </span>
            ) : (
              <span>
                Searching <strong>{validSelected.length}</strong> selected{" "}
                {validSelected.length === 1 ? "document" : "documents"}
              </span>
            )}
          </div>

          {sourceMode === "selected" && validSelected.length ? (
            <div className="source-chips" aria-label="Selected documents">
              {validSelected.map((id) => {
                const document = readyDocuments.find((item) => item.id === id);
                if (!document) return null;
                return (
                  <button
                    key={id}
                    type="button"
                    className="source-chip"
                    aria-label={`Remove ${document.name} from question sources`}
                    onClick={() => toggleSource(id)}
                  >
                    {document.name}
                    <X size={13} aria-hidden="true" />
                  </button>
                );
              })}
            </div>
          ) : null}

          {submissionError ? <ErrorState {...submissionError} /> : null}

          <button
            type="submit"
            className="button button-primary ask-submit"
            disabled={!canSubmit}
          >
            {submission.isPending ? (
              <>
                <span className="button-spinner" aria-hidden="true" />
                Grounding answer…
              </>
            ) : (
              <>
                Ask DocIntel <ArrowRight size={17} aria-hidden="true" />
              </>
            )}
          </button>
          <p className="submission-status" aria-live="polite">
            {submission.isPending
              ? "Retrieving evidence, validating citations, and verifying claim support."
              : ""}
          </p>
        </section>

        <aside className="source-selector" aria-labelledby="source-title">
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">Evidence boundary</span>
              <h2 id="source-title">Choose sources</h2>
            </div>
            <span className="ready-count">
              {readyDocuments.length} READY
            </span>
          </div>

          <label
            className={`source-mode ${sourceMode === "all" ? "active" : ""}`}
          >
            <input
              type="radio"
              name="source-mode"
              checked={sourceMode === "all"}
              onChange={() => setSourceMode("all")}
            />
            <span className="mode-radio" aria-hidden="true" />
            <span>
              <strong>All eligible documents</strong>
              <small>Use every compatible READY source.</small>
            </span>
          </label>
          <label
            className={`source-mode ${sourceMode === "selected" ? "active" : ""}`}
          >
            <input
              type="radio"
              name="source-mode"
              checked={sourceMode === "selected"}
              onChange={() => setSourceMode("selected")}
            />
            <span className="mode-radio" aria-hidden="true" />
            <span>
              <strong>Selected documents</strong>
              <small>Constrain evidence to specific PDFs.</small>
            </span>
          </label>

          {sourceMode === "selected" ? (
            <>
              <label className="search-field source-search">
                <Search size={16} aria-hidden="true" />
                <span className="visually-hidden">Search READY sources</span>
                <input
                  type="search"
                  value={sourceSearch}
                  placeholder="Find a READY document"
                  onChange={(event) => setSourceSearch(event.target.value)}
                />
              </label>
              <div
                className="source-options"
                role="group"
                aria-label="READY documents"
              >
                {filteredSources.map((document) => {
                  const checked = validSelected.includes(document.id);
                  return (
                    <label
                      key={document.id}
                      className={`source-option ${checked ? "selected" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={
                          !checked &&
                          validSelected.length >= QUESTION_MAX_DOCUMENTS
                        }
                        onChange={() => toggleSource(document.id)}
                      />
                      <span className="option-check" aria-hidden="true">
                        {checked ? <Check size={13} /> : null}
                      </span>
                      <FileCheck2 size={17} aria-hidden="true" />
                      <span>
                        <strong title={document.name}>{document.name}</strong>
                        <small>Ready · {formatDate(document.updated_at)}</small>
                      </span>
                    </label>
                  );
                })}
              </div>
              <p className="source-limit">
                {validSelected.length} of {QUESTION_MAX_DOCUMENTS} selected
              </p>
            </>
          ) : null}
        </aside>
      </form>
    </div>
  );
}
