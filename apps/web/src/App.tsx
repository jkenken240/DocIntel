import { useEffect } from "react";

import { AppShell } from "./components/AppShell";
import { EmptyState } from "./components/Feedback";
import { useRouter } from "./lib/router";
import { AskPage } from "./pages/AskPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { QuestionPage } from "./pages/QuestionPage";

function safeRouteId(value: string): string | null {
  try {
    const decoded = decodeURIComponent(value);
    return /^[0-9a-f-]{36}$/i.test(decoded) ? decoded : null;
  } catch {
    return null;
  }
}

export function App() {
  const { pathname } = useRouter();

  let title = "Overview";
  let content = <OverviewPage />;

  if (pathname === "/documents" || pathname === "/documents/") {
    title = "Documents";
    content = <DocumentsPage />;
  } else if (pathname.startsWith("/documents/")) {
    const documentId = safeRouteId(pathname.slice("/documents/".length));
    title = "Document source";
    content = documentId ? (
      <DocumentDetailPage documentId={documentId} />
    ) : (
      <EmptyState
        title="Document route is invalid"
        message="Return to the library and choose a current document."
      />
    );
  } else if (pathname === "/ask" || pathname === "/ask/") {
    title = "Ask DocIntel";
    content = <AskPage />;
  } else if (pathname.startsWith("/questions/")) {
    const questionId = safeRouteId(pathname.slice("/questions/".length));
    title = "Grounded answer";
    content = questionId ? (
      <QuestionPage questionId={questionId} />
    ) : (
      <EmptyState
        title="Question route is invalid"
        message="Return to Ask DocIntel and submit a grounded question."
      />
    );
  } else if (pathname !== "/") {
    title = "Page not found";
    content = (
      <EmptyState
        title="This workspace page does not exist"
        message="Use the DocIntel navigation to return to a current workspace view."
      />
    );
  }

  useEffect(() => {
    document.title = `${title} · DocIntel`;
  }, [title]);

  return <AppShell>{content}</AppShell>;
}
