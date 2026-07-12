"use client";

import { useState } from "react";
import type { CheckResponse, Lang, Source } from "@/lib/types";
import { UI } from "@/lib/i18n";
import { checkMessage } from "@/lib/api";
import ResultCard from "@/components/ResultCard";

const SOURCES: Source[] = [
  "suspicious_msg",
  "health_article",
  "supplement_ad",
  "other",
];

export default function Home() {
  const [lang, setLang] = useState<Lang>("zh");
  const [content, setContent] = useState("");
  const [source, setSource] = useState<Source>("suspicious_msg");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const t = UI[lang];

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await checkMessage({ content, source, lang });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t.title}</h1>
          <p className="mt-2 max-w-lg text-slate-600">{t.tagline}</p>
        </div>
        <div className="flex shrink-0 gap-1 rounded-full bg-white p-1 shadow-sm ring-1 ring-slate-200">
          {(["zh", "en"] as Lang[]).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLang(l)}
              className={`rounded-full px-3 py-1 text-sm font-medium transition ${
                lang === l
                  ? "bg-slate-900 text-white"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              {l === "zh" ? "中文" : "EN"}
            </button>
          ))}
        </div>
      </header>

      <form
        onSubmit={onSubmit}
        className="mt-8 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200"
      >
        <label
          htmlFor="content"
          className="block text-sm font-semibold text-slate-700"
        >
          {t.inputLabel}
        </label>
        <textarea
          id="content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={t.placeholder}
          rows={6}
          maxLength={5000}
          className="mt-2 w-full resize-y rounded-xl border border-slate-300 p-3 text-slate-900 outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900"
        />

        <label
          htmlFor="source"
          className="mt-4 block text-sm font-semibold text-slate-700"
        >
          {t.sourceLabel}
        </label>
        <select
          id="source"
          value={source}
          onChange={(e) => setSource(e.target.value as Source)}
          className="mt-2 w-full rounded-xl border border-slate-300 bg-white p-3 text-slate-900 outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900"
        >
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {t.sources[s]}
            </option>
          ))}
        </select>

        <button
          type="submit"
          disabled={loading || !content.trim()}
          className="mt-6 w-full rounded-xl bg-slate-900 px-4 py-3 font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? t.checking : t.submit}
        </button>
      </form>

      {error && (
        <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4">
          <h2 className="text-sm font-semibold text-red-700">{t.errorTitle}</h2>
          <p className="mt-1 text-sm text-red-600">{error}</p>
        </div>
      )}

      {result && (
        <div className="mt-6">
          <ResultCard result={result} lang={lang} />
        </div>
      )}

      <footer className="mt-10 text-center text-xs text-slate-400">
        {t.poweredBy}
      </footer>
    </main>
  );
}
