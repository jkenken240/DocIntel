import { useQueryClient } from "@tanstack/react-query";
import { FileUp, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import {
  type ChangeEvent,
  type DragEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { describeError } from "../lib/api/client";
import { uploadDocument } from "../lib/api/documents";
import { formatBytes } from "../lib/format";

type UploadState = "queued" | "uploading" | "error";

interface UploadItem {
  id: string;
  fingerprint: string;
  file: File;
  state: UploadState;
  progress: number;
  message: string | null;
  retryable: boolean;
}

const MAX_QUEUE_SIZE = 20;
const UPLOAD_CONCURRENCY = 2;

function uploadId(): string {
  return globalThis.crypto?.randomUUID?.() ??
    `upload-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function fingerprint(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function validatePdf(file: File): string | null {
  if (!file.name.toLocaleLowerCase().endsWith(".pdf")) {
    return "Choose a file with a .pdf extension.";
  }
  if (file.type && file.type !== "application/pdf") {
    return "This file does not report the PDF media type.";
  }
  return null;
}

export function UploadQueue({
  autoFocus = false,
}: {
  autoFocus?: boolean;
}) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const activeIds = useRef(new Set<string>());
  const controllers = useRef(new Map<string, AbortController>());
  const acceptedFingerprints = useRef(new Set<string>());
  const mounted = useRef(true);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    mounted.current = true;
    const activeControllers = controllers.current;
    return () => {
      mounted.current = false;
      activeControllers.forEach((controller) => controller.abort());
      activeControllers.clear();
    };
  }, []);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  const runUpload = useCallback(
    async (item: UploadItem) => {
      activeIds.current.add(item.id);
      const controller = new AbortController();
      controllers.current.set(item.id, controller);
      setItems((current) =>
        current.map((candidate) =>
          candidate.id === item.id
            ? { ...candidate, state: "uploading", progress: 0, message: null }
            : candidate,
        ),
      );

      try {
        await uploadDocument(item.file, {
          signal: controller.signal,
          onProgress: (progress) => {
            if (!mounted.current) return;
            setItems((current) =>
              current.map((candidate) =>
                candidate.id === item.id
                  ? { ...candidate, progress }
                  : candidate,
              ),
            );
          },
        });
        if (mounted.current) {
          acceptedFingerprints.current.add(item.fingerprint);
          setAnnouncement(
            `${item.file.name} uploaded and queued for processing.`,
          );
          setItems((current) =>
            current.filter((candidate) => candidate.id !== item.id),
          );
          await queryClient.invalidateQueries({ queryKey: ["documents"] });
        }
      } catch (error) {
        if (mounted.current && !(error instanceof DOMException && error.name === "AbortError")) {
          setItems((current) =>
            current.map((candidate) =>
              candidate.id === item.id
                  ? {
                    ...candidate,
                    state: "error",
                    message: describeError(error).message,
                    retryable: true,
                  }
                : candidate,
            ),
          );
        }
      } finally {
        activeIds.current.delete(item.id);
        controllers.current.delete(item.id);
        if (mounted.current) setItems((current) => [...current]);
      }
    },
    [queryClient],
  );

  useEffect(() => {
    const slots = UPLOAD_CONCURRENCY - activeIds.current.size;
    if (slots <= 0) return;
    items
      .filter(
        (item) => item.state === "queued" && !activeIds.current.has(item.id),
      )
      .slice(0, slots)
      .forEach((item) => void runUpload(item));
  }, [items, runUpload]);

  const addFiles = useCallback((files: File[]) => {
    setAnnouncement("");
    setItems((current) => {
      const known = new Set([
        ...acceptedFingerprints.current,
        ...current.map((item) => item.fingerprint),
      ]);
      const room = Math.max(0, MAX_QUEUE_SIZE - current.length);
      return [
        ...current,
        ...files.slice(0, room).flatMap((file) => {
          const fileFingerprint = fingerprint(file);
          if (known.has(fileFingerprint)) return [];
          known.add(fileFingerprint);
          const validation = validatePdf(file);
          return [
            {
              id: uploadId(),
              fingerprint: fileFingerprint,
              file,
              state: validation ? ("error" as const) : ("queued" as const),
              progress: 0,
              message: validation,
              retryable: !validation,
            },
          ];
        }),
      ];
    });
  }, []);

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    addFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    addFiles(Array.from(event.dataTransfer.files));
  }

  function retry(itemId: string) {
    setItems((current) =>
      current.map((item) =>
        item.id === itemId
          ? { ...item, state: "queued", progress: 0, message: null }
          : item,
      ),
    );
  }

  function dismiss(itemId: string) {
    controllers.current.get(itemId)?.abort();
    setItems((current) => current.filter((item) => item.id !== itemId));
  }

  const activeCount = items.filter(
    (item) => item.state === "queued" || item.state === "uploading",
  ).length;

  return (
    <section className="upload-panel" aria-labelledby="upload-title">
      <div className="section-heading compact">
        <div>
          <span className="eyebrow">Protected intake</span>
          <h2 id="upload-title">Upload PDFs</h2>
          <p>
            Select up to {MAX_QUEUE_SIZE} PDFs. DocIntel sends two at a time and
            validates every file on the server.
          </p>
        </div>
        {activeCount > 0 ? (
          <span className="queue-count">{activeCount} active</span>
        ) : null}
      </div>

      <div
        className={`drop-zone ${dragActive ? "drag-active" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (event.currentTarget === event.target) setDragActive(false);
        }}
        onDrop={handleDrop}
      >
        <UploadCloud size={29} aria-hidden="true" />
        <div>
          <strong>Drop PDFs here</strong>
          <span>or choose files from this device</span>
        </div>
        <button
          type="button"
          className="button button-secondary"
          onClick={() => inputRef.current?.click()}
        >
          <FileUp size={17} aria-hidden="true" />
          Choose PDFs
        </button>
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept=".pdf,application/pdf"
          multiple
          onChange={handleInput}
          aria-label="Choose PDF files"
        />
      </div>

      <p
        className="visually-hidden"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {announcement}
      </p>

      {items.length ? (
        <ul className="upload-list" aria-label="Upload queue">
          {items.map((item) => (
            <li key={item.id} className={`upload-row upload-${item.state}`}>
              <div className="file-symbol">
                <FileUp size={18} aria-hidden="true" />
              </div>
              <div className="upload-copy">
                <strong title={item.file.name}>{item.file.name}</strong>
                <span>
                  {formatBytes(item.file.size)}
                  {item.message ? ` · ${item.message}` : ""}
                </span>
                {item.state === "uploading" ? (
                  <div
                    className="progress-track"
                    role="progressbar"
                    aria-label={`Uploading ${item.file.name}`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={item.progress}
                  >
                    <span style={{ width: `${item.progress}%` }} />
                  </div>
                ) : null}
              </div>
              <div className="upload-actions">
                {item.state === "error" && item.retryable ? (
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Retry ${item.file.name}`}
                    onClick={() => retry(item.id)}
                  >
                    <RefreshCw size={17} aria-hidden="true" />
                  </button>
                ) : null}
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Dismiss ${item.file.name}`}
                  disabled={item.state === "uploading"}
                  onClick={() => dismiss(item.id)}
                >
                  <Trash2 size={17} aria-hidden="true" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
