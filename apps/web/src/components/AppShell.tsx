import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  FileStack,
  Library,
  MessageSquareText,
  Orbit,
} from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";

import { fetchReadiness } from "../lib/api/health";
import { AppLink, useRouter } from "../lib/router";

const navigation = [
  { to: "/", label: "Overview", icon: Orbit },
  { to: "/documents", label: "Documents", icon: Library },
  { to: "/ask", label: "Ask DocIntel", icon: MessageSquareText },
];

function isActive(pathname: string, destination: string): boolean {
  if (destination === "/") return pathname === "/";
  if (destination === "/ask") {
    return pathname.startsWith("/ask") || pathname.startsWith("/questions/");
  }
  return pathname.startsWith(destination);
}

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useRouter();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      mainRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pathname]);

  const readiness = useQuery({
    queryKey: ["platform-readiness"],
    queryFn: ({ signal }) => fetchReadiness(signal),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.status === "ready" ? 30_000 : 10_000,
  });
  const ready = readiness.data?.status === "ready";

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace-main">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <AppLink to="/" className="brand-lockup" aria-label="DocIntel overview">
          <span className="brand-mark" aria-hidden="true">
            <FileStack size={19} />
          </span>
          <span>
            <strong>DocIntel</strong>
            <small>Evidence workspace</small>
          </span>
        </AppLink>

        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map(({ to, label, icon: Icon }) => (
            <AppLink
              key={to}
              to={to}
              className={`nav-link ${isActive(pathname, to) ? "active" : ""}`}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </AppLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div
            className={`runtime-card ${ready ? "runtime-ready" : "runtime-warning"}`}
            role="status"
            aria-live="polite"
          >
            <span className="runtime-dot" aria-hidden="true" />
            <span>
              <strong>
                {readiness.isPending
                  ? "Checking workspace"
                  : ready
                    ? "Workspace ready"
                    : "Workspace unavailable"}
              </strong>
              <small>
                {ready
                  ? "Local services · mock intelligence"
                  : "Check the local API services"}
              </small>
            </span>
          </div>
          <p className="privacy-note">
            PDFs stay in your configured protected storage.
          </p>
        </div>
      </aside>

      <header className="mobile-header">
        <AppLink to="/" className="brand-lockup" aria-label="DocIntel overview">
          <span className="brand-mark" aria-hidden="true">
            <FileStack size={18} />
          </span>
          <strong>DocIntel</strong>
        </AppLink>
        <span className={`mobile-health ${ready ? "ready" : ""}`}>
          <Activity size={15} aria-hidden="true" />
          {ready ? "Ready" : "Offline"}
        </span>
      </header>

      <main
        ref={mainRef}
        id="workspace-main"
        className="workspace-main"
        tabIndex={-1}
      >
        {readiness.isError ? (
          <div className="global-warning" role="alert">
            <span>DocIntel cannot reach the local workspace API.</span>
            <button
              type="button"
              className="text-button"
              onClick={() => void readiness.refetch()}
            >
              Check again <ArrowUpRight size={14} aria-hidden="true" />
            </button>
          </div>
        ) : null}
        {children}
      </main>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {navigation.map(({ to, label, icon: Icon }) => (
          <AppLink
            key={to}
            to={to}
            className={`mobile-nav-link ${isActive(pathname, to) ? "active" : ""}`}
          >
            <Icon size={19} aria-hidden="true" />
            <span>{label}</span>
          </AppLink>
        ))}
      </nav>
    </div>
  );
}
