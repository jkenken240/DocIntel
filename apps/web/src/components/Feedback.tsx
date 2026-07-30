import {
  AlertCircle,
  CheckCircle2,
  FileSearch,
  LoaderCircle,
} from "lucide-react";
import type { ReactNode } from "react";

export function LoadingState({
  title = "Loading workspace",
  message = "DocIntel is assembling the latest information.",
}: {
  title?: string;
  message?: string;
}) {
  return (
    <div className="feedback-state" role="status" aria-live="polite">
      <LoaderCircle className="feedback-icon spin" aria-hidden="true" />
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="feedback-state feedback-empty">
      <FileSearch className="feedback-icon" aria-hidden="true" />
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
        {action ? <div className="feedback-action">{action}</div> : null}
      </div>
    </div>
  );
}

export function ErrorState({
  title,
  message,
  traceId,
  action,
}: {
  title: string;
  message: string;
  traceId?: string | null;
  action?: ReactNode;
}) {
  return (
    <div className="feedback-state feedback-error" role="alert">
      <AlertCircle className="feedback-icon" aria-hidden="true" />
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
        {traceId ? <p className="trace-id">Support trace: {traceId}</p> : null}
        {action ? <div className="feedback-action">{action}</div> : null}
      </div>
    </div>
  );
}

export function SuccessNotice({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="success-notice" role="status">
      <CheckCircle2 size={17} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
