import type { Lang, Risk, Source } from "./types";

// UI chrome only. The verdict text (summary / advice / reasons) is localized
// server-side by the Flask API based on the `lang` we send.

export const UI: Record<Lang, {
  title: string;
  tagline: string;
  inputLabel: string;
  placeholder: string;
  sourceLabel: string;
  submit: string;
  checking: string;
  sources: Record<Source, string>;
  risk: Record<Risk, string>;
  aiSecondOpinion: string;
  toolsUsed: string;
  whatToDo: string;
  childMessage: string;
  emergency: string;
  errorTitle: string;
  poweredBy: string;
}> = {
  zh: {
    title: "爸妈求证",
    tagline: "把可疑的短信、链接或养生广告贴进来，几秒钟得到通俗的风险判断。",
    inputLabel: "要检查的内容",
    placeholder: "粘贴短信、链接或广告文字……",
    sourceLabel: "内容来源",
    submit: "开始检查",
    checking: "检查中……",
    sources: {
      health_article: "养生文章",
      supplement_ad: "保健品广告",
      suspicious_msg: "可疑短信",
      other: "其他",
    },
    risk: { ok: "安全", caution: "可疑", danger: "高危" },
    aiSecondOpinion: "AI 二次核查",
    toolsUsed: "AI 调用的工具",
    whatToDo: "现在该怎么做",
    childMessage: "可以转发给家人的提醒",
    emergency: "紧急电话",
    errorTitle: "出错了",
    poweredBy: "规则引擎 + LangGraph AI 二次核查 · 风险只增不降",
  },
  en: {
    title: "Parent Check",
    tagline:
      "Paste a suspicious message, link or health ad and get a plain-language risk check in seconds.",
    inputLabel: "Content to check",
    placeholder: "Paste a message, link or ad text…",
    sourceLabel: "Where is it from?",
    submit: "Check it",
    checking: "Checking…",
    sources: {
      health_article: "Health article",
      supplement_ad: "Supplement ad",
      suspicious_msg: "Suspicious message",
      other: "Other",
    },
    risk: { ok: "Safe", caution: "Caution", danger: "High risk" },
    aiSecondOpinion: "AI second opinion",
    toolsUsed: "Tools the AI used",
    whatToDo: "What to do now",
    childMessage: "A note you can forward to family",
    emergency: "Emergency number",
    errorTitle: "Something went wrong",
    poweredBy: "Rule engine + LangGraph AI second opinion · risk only ever rises",
  },
};

export const RISK_STYLES: Record<Risk, { badge: string; ring: string; dot: string }> = {
  ok: {
    badge: "bg-emerald-100 text-emerald-800",
    ring: "ring-emerald-200",
    dot: "bg-emerald-500",
  },
  caution: {
    badge: "bg-amber-100 text-amber-800",
    ring: "ring-amber-200",
    dot: "bg-amber-500",
  },
  danger: {
    badge: "bg-red-100 text-red-800",
    ring: "ring-red-300",
    dot: "bg-red-500",
  },
};
