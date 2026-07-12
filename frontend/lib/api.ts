import type { CheckRequest, CheckResponse } from "./types";

// The Flask backend origin. Defaults to the docker-compose web service port
// (8000). Override with NEXT_PUBLIC_API_BASE for other environments.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function checkMessage(
  req: CheckRequest,
): Promise<CheckResponse> {
  const res = await fetch(`${API_BASE}/api/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    // The API returns { error, message? } on failure.
    const body = await res.json().catch(() => ({}) as Record<string, string>);
    throw new Error(body.message || body.error || `Request failed (${res.status})`);
  }

  return (await res.json()) as CheckResponse;
}
