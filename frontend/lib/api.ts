import type { CheckRequest, CheckResponse, Lang, Source } from "./types";

// The Flask backend origin. Defaults to the docker-compose web service port
// (8000). Override with NEXT_PUBLIC_API_BASE for other environments.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function parseCheckResponse(value: unknown, lang: Lang = "en"): CheckResponse {
  const invalid = lang === "zh" ? "服务返回的结果不完整，请稍后重试。" : "Invalid analysis response";
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(invalid);
  }
  const data = value as Record<string, unknown>;
  const strings = ["category", "summary", "child_message", "ai_reason", "ai_advice", "emergency_number", "fetched_title"];
  const lists = ["reasons", "advice", "ai_tools", "actions"];
  if (!["ok", "caution", "danger"].includes(String(data.risk)) ||
      typeof data.used_ai !== "boolean" ||
      strings.some((key) => typeof data[key] !== "string") ||
      lists.some((key) => !Array.isArray(data[key]) || !(data[key] as unknown[]).every((item) => typeof item === "string"))) {
    throw new Error(invalid);
  }
  return data as unknown as CheckResponse;
}

function responseError(body: Record<string, unknown>, status: number, lang: Lang): Error {
  if (typeof body.message === "string" && body.message) return new Error(body.message);
  const message = status === 429
    ? (lang === "zh" ? "请求较多，请稍后再试。" : "Too many requests. Please try again shortly.")
    : status === 413
      ? (lang === "zh" ? "内容太大，请缩短文字或压缩图片后重试。" : "Please shorten the text or use a smaller image.")
      : (lang === "zh" ? "暂时无法完成检查，请稍后重试。" : "The check could not be completed. Please try again shortly.");
  return new Error(message);
}

export async function checkMessage(
  req: CheckRequest,
): Promise<CheckResponse> {
  const res = await fetch(`${API_BASE}/api/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal: AbortSignal.timeout(90_000),
  });

  if (!res.ok) {
    // The API returns { error, message? } on failure.
    const body = await res.json().catch(() => ({}) as Record<string, string>);
    throw responseError(body, res.status, req.lang);
  }

  return parseCheckResponse(await res.json(), req.lang);
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
    signal: AbortSignal.timeout(90_000),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}) as Record<string, string>);
    throw responseError(body, res.status, lang);
  }

  return parseCheckResponse(await res.json(), lang);
}
