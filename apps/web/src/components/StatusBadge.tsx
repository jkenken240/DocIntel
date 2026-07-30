import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  LoaderCircle,
  Trash2,
} from "lucide-react";

import type {
  DocumentStage,
  DocumentStatus,
} from "../lib/api/contracts";
import {
  progressLabel,
  progressPercent,
  stageLabel,
  statusLabel,
} from "../lib/format";
import type { DocumentProgress } from "../lib/api/contracts";

const icons = {
  queued: Clock3,
  processing: LoaderCircle,
  ready: CheckCircle2,
  failed: AlertTriangle,
  deleting: Trash2,
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const Icon = icons[status];
  return (
    <span className={`status-badge status-${status}`}>
      <Icon
        size={14}
        className={status === "processing" ? "spin" : undefined}
        aria-hidden="true"
      />
      {statusLabel(status)}
    </span>
  );
}

export function LifecycleProgress({
  status,
  stage,
  progress,
  compact = false,
}: {
  status: DocumentStatus;
  stage: DocumentStage;
  progress: DocumentProgress;
  compact?: boolean;
}) {
  const percent = progressPercent(progress);
  if (status === "ready") {
    return <span className="lifecycle-complete">Evidence ready</span>;
  }
  if (status === "failed") {
    return <span className="lifecycle-failed">Processing stopped safely</span>;
  }

  return (
    <div className={compact ? "lifecycle lifecycle-compact" : "lifecycle"}>
      <div className="lifecycle-copy">
        <span>{stageLabel(stage)}</span>
        <span>{progressLabel(progress)}</span>
      </div>
      <div
        className={`progress-track ${percent === null ? "progress-indeterminate" : ""}`}
        role="progressbar"
        aria-label={`${stageLabel(stage)}: ${progressLabel(progress)}`}
        aria-valuemin={0}
        aria-valuemax={percent === null ? undefined : 100}
        aria-valuenow={percent ?? undefined}
      >
        <span style={percent === null ? undefined : { width: `${percent}%` }} />
      </div>
    </div>
  );
}
