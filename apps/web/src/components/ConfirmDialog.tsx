import { AlertTriangle, X } from "lucide-react";
import { useEffect, useRef } from "react";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [busy, onCancel, open]);

  if (!open) return null;

  return (
    <div className="dialog-backdrop">
      <section
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-description"
      >
        <div className="dialog-heading">
          <div className="dialog-symbol">
            <AlertTriangle size={21} aria-hidden="true" />
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="Close confirmation"
            disabled={busy}
            onClick={onCancel}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <h2 id="confirm-title">{title}</h2>
        <p id="confirm-description">{description}</p>
        <div className="dialog-actions">
          <button
            ref={cancelRef}
            type="button"
            className="button button-secondary"
            disabled={busy}
            onClick={onCancel}
          >
            Keep document
          </button>
          <button
            type="button"
            className="button button-danger"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "Requesting deletion…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
