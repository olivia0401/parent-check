import type { CheckResponse } from "../lib/types";

export const result: CheckResponse = {
  risk: "danger", category: "scam", reasons: [], summary: "Suspicious message",
  advice: ["Do not transfer money", "Do not share codes"], child_message: "Ask family",
  ai_reason: "", ai_advice: "", ai_tools: [], actions: [], emergency_number: "",
  fetched_title: "", used_ai: false,
};
