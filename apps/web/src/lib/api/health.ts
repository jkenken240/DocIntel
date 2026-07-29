export type ComponentStatus = "ready" | "not_ready";

export interface ComponentCheck {
  status: ComponentStatus;
  detail: string;
}

export interface ReadinessResponse {
  status: ComponentStatus;
  checks: Record<string, ComponentCheck>;
}

const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function fetchReadiness(
  signal?: AbortSignal,
): Promise<ReadinessResponse> {
  const response = await fetch(`${apiBaseUrl}/health/ready`, {
    headers: { Accept: "application/json" },
    signal,
  });

  if (response.status !== 200 && response.status !== 503) {
    throw new Error(`Unexpected readiness response: HTTP ${response.status}`);
  }

  return (await response.json()) as ReadinessResponse;
}
