export type Lang = "zh" | "en";

export type Risk = "ok" | "caution" | "danger";

export type Source =
  | "health_article"
  | "supplement_ad"
  | "suspicious_msg"
  | "other";

export interface CheckRequest {
  content: string;
  source: Source;
  lang: Lang;
}

export interface CheckResponse {
  risk: Risk;
  category: string;
  reasons: string[];
  summary: string;
  advice: string;
  child_message: string;
  ai_reason: string;
  ai_advice: string;
  ai_tools: string[];
  actions: string[];
  emergency_number: string;
  fetched_title: string;
  used_ai: boolean;
}
