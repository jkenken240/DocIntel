import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw } from "lucide-react";

import { AnswerWorkspace } from "../components/AnswerWorkspace";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { ApiProblem, describeError } from "../lib/api/client";
import { getQuestion } from "../lib/api/questions";
import { AppLink } from "../lib/router";

export function QuestionPage({ questionId }: { questionId: string }) {
  const question = useQuery({
    queryKey: ["question", questionId],
    queryFn: ({ signal }) => getQuestion(questionId, signal),
    retry: false,
  });

  if (question.isPending) {
    return (
      <div className="page-frame question-result-page">
        <LoadingState
          title="Restoring grounded result"
          message="Loading persisted claims, citations, and evidence."
        />
      </div>
    );
  }

  if (question.isError) {
    if (
      question.error instanceof ApiProblem &&
      question.error.status === 404
    ) {
      return (
        <div className="page-frame question-result-page">
          <EmptyState
            title="This grounded result is no longer available"
            message="A cited source may have been deleted, so DocIntel will not present the previous answer as valid."
            action={
              <div className="button-row">
                <AppLink to="/ask" className="button button-primary">
                  Ask a new question
                </AppLink>
                <AppLink to="/documents" className="button button-secondary">
                  Review documents
                </AppLink>
              </div>
            }
          />
        </div>
      );
    }
    return (
      <div className="page-frame question-result-page">
        <ErrorState
          {...describeError(question.error)}
          action={
            <button
              type="button"
              className="button button-secondary"
              onClick={() => void question.refetch()}
            >
              <RefreshCw size={16} aria-hidden="true" />
              Try again
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="page-frame question-result-page">
      <AppLink to="/ask" className="back-link">
        <ArrowLeft size={16} aria-hidden="true" />
        Ask another question
      </AppLink>
      <AnswerWorkspace result={question.data} />
    </div>
  );
}
