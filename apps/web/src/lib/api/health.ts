import { API_BASE_URL } from "./client";
import type { ReadinessResponse } from "./contracts";

export async function fetchReadiness(
  signal?: AbortSignal,
): Promise<ReadinessResponse> {
  const response = await fetch(`${API_BASE_URL}/health/ready`, {
    headers: { Accept: "application/json" },
    signal,
  });

  if (response.status !== 200 && response.status !== 503) {
    throw new Error(`Unexpected readiness response: HTTP ${response.status}`);
  }

  return (await response.json()) as ReadinessResponse;
}
