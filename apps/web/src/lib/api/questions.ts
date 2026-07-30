import { requestJson } from "./client";
import type { QuestionResponse } from "./contracts";

export const QUESTION_MAX_CHARS = 2000;
export const QUESTION_MAX_DOCUMENTS = 20;

export function askQuestion(
  question: string,
  documentIds: string[],
  signal?: AbortSignal,
): Promise<QuestionResponse> {
  return requestJson<QuestionResponse>("/questions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      document_ids: documentIds,
    }),
    signal,
  });
}

export function getQuestion(
  questionId: string,
  signal?: AbortSignal,
): Promise<QuestionResponse> {
  return requestJson<QuestionResponse>(
    `/questions/${encodeURIComponent(questionId)}`,
    { signal },
  );
}
