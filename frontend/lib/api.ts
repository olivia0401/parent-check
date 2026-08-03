import type { CheckRequest, CheckResponse, Lang, Source } from "./types";

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

// Upload a screenshot instead of pasting text: the backend OCRs it and runs the
// exact same check. Uses multipart/form-data, so no JSON Content-Type header.
export async function checkImage(
  file: File,
  source: Source,
  lang: Lang,
): Promise<CheckResponse> {
  const form = new FormData();
  form.append("image", file);
  form.append("source", source);
  form.append("lang", lang);

  const res = await fetch(`${API_BASE}/api/check-image`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}) as Record<string, string>);
    throw new Error(body.message || body.error || `Request failed (${res.status})`);
  }

  return (await res.json()) as CheckResponse;
}
