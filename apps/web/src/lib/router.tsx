/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  type MouseEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

interface RouterValue {
  path: string;
  pathname: string;
  search: URLSearchParams;
  navigate: (to: string, options?: { replace?: boolean }) => void;
}

const RouterContext = createContext<RouterValue | null>(null);

function currentPath(): string {
  return `${window.location.pathname}${window.location.search}`;
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    const handlePopState = () => setPath(currentPath());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = useCallback(
    (to: string, options: { replace?: boolean } = {}) => {
      if (options.replace) {
        window.history.replaceState(null, "", to);
      } else {
        window.history.pushState(null, "", to);
      }
      setPath(currentPath());
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [],
  );

  const value = useMemo<RouterValue>(() => {
    const url = new URL(path, window.location.origin);
    return {
      path,
      pathname: url.pathname,
      search: url.searchParams,
      navigate,
    };
  }, [navigate, path]);

  return (
    <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
  );
}

export function useRouter(): RouterValue {
  const value = useContext(RouterContext);
  if (!value) throw new Error("useRouter must be used inside RouterProvider.");
  return value;
}

export function AppLink({
  to,
  children,
  className,
  title,
  "aria-label": ariaLabel,
}: {
  to: string;
  children: ReactNode;
  className?: string;
  title?: string;
  "aria-label"?: string;
}) {
  const { navigate } = useRouter();

  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.button === 0 &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.shiftKey &&
      !event.altKey
    ) {
      event.preventDefault();
      navigate(to);
    }
  }

  return (
    <a
      href={to}
      className={className}
      title={title}
      aria-label={ariaLabel}
      onClick={handleClick}
    >
      {children}
    </a>
  );
}
