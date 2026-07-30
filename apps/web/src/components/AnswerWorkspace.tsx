import {
  ArrowLeft,
  ArrowRight,
  BookOpenCheck,
  FileSearch,
  Link2,
  MessageSquareQuote,
  ShieldCheck,
} from "lucide-react";
import {
  Fragment,
  type ReactNode,
  useMemo,
  useState,
} from "react";

import type {
  CitationRecord,
  ClaimRecord,
  QuestionResponse,
} from "../lib/api/contracts";
import { formatDate, reasonLabel } from "../lib/format";
import { AppLink } from "../lib/router";
import { PdfViewer } from "./PdfViewer";

function citationLabel(citation: CitationRecord): string {
  return `${citation.filename}, page ${citation.page_number}`;
}

function AnswerText({
  answer,
  claims,
  activeClaimId,
  onClaim,
}: {
  answer: string;
  claims: ClaimRecord[];
  activeClaimId: string | null;
  onClaim: (claim: ClaimRecord) => void;
}) {
  const content = useMemo<ReactNode[]>(() => {
    const ordered = [...claims].sort((left, right) => left.char_start - right.char_start);
    const nodes: ReactNode[] = [];
    let cursor = 0;
    for (const claim of ordered) {
      if (
        claim.char_start < cursor ||
        claim.char_end > answer.length ||
        answer.slice(claim.char_start, claim.char_end) !== claim.text
      ) {
        continue;
      }
      if (claim.char_start > cursor) {
        nodes.push(
          <Fragment key={`text-${cursor}`}>
            {answer.slice(cursor, claim.char_start)}
          </Fragment>,
        );
      }
      nodes.push(
        <button
          type="button"
          key={claim.id}
          className={`answer-claim-span ${activeClaimId === claim.id ? "active" : ""}`}
          aria-label={`Inspect claim ${claim.ordinal + 1}: ${claim.text}`}
          aria-pressed={activeClaimId === claim.id}
          onClick={() => onClaim(claim)}
        >
          {claim.text}
          <sup>{claim.ordinal + 1}</sup>
        </button>,
      );
      cursor = claim.char_end;
    }
    if (cursor < answer.length) nodes.push(answer.slice(cursor));
    return nodes.length ? nodes : [answer];
  }, [activeClaimId, answer, claims, onClaim]);

  return <p className="answer-text">{content}</p>;
}

function AnswerWorkspaceContent({ result }: { result: QuestionResponse }) {
  const citations = useMemo(
    () =>
      result.claims.flatMap((claim) =>
        claim.citations.map((citation) => ({ claim, citation })),
      ),
    [result.claims],
  );
  const [activeClaimId, setActiveClaimId] = useState<string | null>(
    result.claims[0]?.id ?? null,
  );
  const [activeCitationId, setActiveCitationId] = useState<string | null>(
    citations[0]?.citation.id ?? null,
  );

  if (result.status === "insufficient_evidence") {
    return (
      <section className="insufficient-panel" aria-labelledby="insufficient-title">
        <div className="insufficient-symbol">
          <FileSearch size={27} aria-hidden="true" />
        </div>
        <span className="eyebrow">Grounding safeguard</span>
        <h1 id="insufficient-title">The evidence was not strong enough</h1>
        <p className="insufficient-question">“{result.question}”</p>
        <p>{reasonLabel(result.insufficient_reason_code)}</p>
        <p className="muted">
          DocIntel did not display an answer or citations because they could not
          be verified against the selected sources.
        </p>
        <div className="button-row">
          <AppLink
            to={`/ask${result.selected_document_ids.length ? `?documents=${result.selected_document_ids.join(",")}` : ""}`}
            className="button button-primary"
          >
            Revise question
          </AppLink>
          <AppLink to="/documents" className="button button-secondary">
            Choose other sources
          </AppLink>
        </div>
      </section>
    );
  }

  if (!result.answer_text || !result.claims.length) {
    return (
      <section className="insufficient-panel" role="alert">
        <FileSearch size={27} aria-hidden="true" />
        <h1>Grounded answer unavailable</h1>
        <p>The persisted result did not contain a complete supported answer.</p>
      </section>
    );
  }

  const activeEntry =
    citations.find(({ citation }) => citation.id === activeCitationId) ??
    citations[0] ??
    null;
  const activeCitation = activeEntry?.citation ?? null;
  const activeCitationIndex = activeEntry
    ? citations.findIndex(({ citation }) => citation.id === activeEntry.citation.id)
    : -1;

  function activateClaim(claim: ClaimRecord) {
    setActiveClaimId(claim.id);
    if (claim.citations[0]) setActiveCitationId(claim.citations[0].id);
  }

  return (
    <div className="answer-workspace">
      <section className="answer-column" aria-labelledby="answer-title">
        <div className="answer-kicker">
          <span>
            <ShieldCheck size={16} aria-hidden="true" />
            Grounded answer
          </span>
          <span>{result.evidence.length} evidence records</span>
        </div>
        <h1 id="answer-title">{result.question}</h1>
        <AnswerText
          answer={result.answer_text}
          claims={result.claims}
          activeClaimId={activeClaimId}
          onClaim={activateClaim}
        />

        <div className="answer-meta">
          <span>{formatDate(result.created_at)}</span>
          <span>
            Verified by {result.verifier_provider.model}
          </span>
        </div>

        <section className="claims-section" aria-labelledby="claims-title">
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">Structured grounding</span>
              <h2 id="claims-title">Claims and citations</h2>
            </div>
          </div>
          <ol className="claims-list">
            {result.claims.map((claim) => (
              <li
                key={claim.id}
                className={`claim-card ${activeClaimId === claim.id ? "active" : ""}`}
              >
                <button
                  type="button"
                  className="claim-focus"
                  aria-pressed={activeClaimId === claim.id}
                  onClick={() => activateClaim(claim)}
                >
                  <span className="claim-number">{claim.ordinal + 1}</span>
                  <span>
                    <strong>{claim.text}</strong>
                    <small>
                      <BookOpenCheck size={14} aria-hidden="true" />
                      Verified against {claim.citations.length}{" "}
                      {claim.citations.length === 1 ? "citation" : "citations"}
                    </small>
                  </span>
                </button>
                <div className="citation-buttons">
                  {claim.citations.map((citation, index) => (
                    <button
                      type="button"
                      key={citation.id}
                      className={`citation-button ${activeCitationId === citation.id ? "active" : ""}`}
                      aria-pressed={activeCitationId === citation.id}
                      aria-label={`Open citation ${index + 1} for claim ${claim.ordinal + 1}: ${citationLabel(citation)}`}
                      onClick={() => {
                        setActiveClaimId(claim.id);
                        setActiveCitationId(citation.id);
                      }}
                    >
                      <Link2 size={14} aria-hidden="true" />
                      [{claim.ordinal + 1}.{index + 1}] {citation.filename} · p.
                      {citation.page_number}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </section>
      </section>

      <aside className="evidence-column" aria-label="Citation evidence and PDF source">
        {activeCitation ? (
          <>
            <section className="evidence-panel" aria-labelledby="evidence-title">
              <div className="evidence-heading">
                <div>
                  <span className="eyebrow">Exact source evidence</span>
                  <h2 id="evidence-title">{activeCitation.filename}</h2>
                </div>
                <span className="page-chip">Page {activeCitation.page_number}</span>
              </div>
              <div className="evidence-facts">
                <span>Rank {activeCitation.retrieval_rank}</span>
                <span>
                  Characters {activeCitation.char_start}–{activeCitation.char_end}
                </span>
              </div>
              <blockquote>{activeCitation.excerpt}</blockquote>
              <div className="evidence-navigation">
                <button
                  type="button"
                  className="button button-secondary button-small"
                  disabled={activeCitationIndex <= 0}
                  onClick={() => {
                    const previous = citations[activeCitationIndex - 1];
                    if (previous) {
                      setActiveClaimId(previous.claim.id);
                      setActiveCitationId(previous.citation.id);
                    }
                  }}
                >
                  <ArrowLeft size={15} aria-hidden="true" />
                  Previous
                </button>
                <span>
                  {activeCitationIndex + 1} of {citations.length}
                </span>
                <button
                  type="button"
                  className="button button-secondary button-small"
                  disabled={activeCitationIndex >= citations.length - 1}
                  onClick={() => {
                    const next = citations[activeCitationIndex + 1];
                    if (next) {
                      setActiveClaimId(next.claim.id);
                      setActiveCitationId(next.citation.id);
                    }
                  }}
                >
                  Next
                  <ArrowRight size={15} aria-hidden="true" />
                </button>
              </div>
            </section>
            <PdfViewer
              key={activeCitation.document_id}
              documentId={activeCitation.document_id}
              filename={activeCitation.filename}
              initialPage={activeCitation.page_number}
            />
          </>
        ) : (
          <div className="feedback-state">
            <MessageSquareQuote size={24} aria-hidden="true" />
            <div>
              <h2>Select a citation</h2>
              <p>Choose a grounded claim to inspect its exact source.</p>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

export function AnswerWorkspace({ result }: { result: QuestionResponse }) {
  return <AnswerWorkspaceContent key={result.id} result={result} />;
}
