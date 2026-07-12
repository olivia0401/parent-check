import type { CheckResponse, Lang } from "@/lib/types";
import { RISK_STYLES, UI } from "@/lib/i18n";

export default function ResultCard({
  result,
  lang,
}: {
  result: CheckResponse;
  lang: Lang;
}) {
  const t = UI[lang];
  const style = RISK_STYLES[result.risk];

  return (
    <section
      className={`rounded-2xl bg-white p-6 shadow-sm ring-1 ${style.ring}`}
      aria-live="polite"
    >
      <div className="flex items-center gap-3">
        <span className={`h-3 w-3 rounded-full ${style.dot}`} aria-hidden />
        <span
          className={`rounded-full px-3 py-1 text-sm font-semibold ${style.badge}`}
        >
          {t.risk[result.risk]}
        </span>
        {result.fetched_title && (
          <span className="truncate text-sm text-slate-500">
            {result.fetched_title}
          </span>
        )}
      </div>

      {result.summary && (
        <p className="mt-4 text-lg font-medium text-slate-800">
          {result.summary}
        </p>
      )}

      {result.reasons.length > 0 && (
        <ul className="mt-4 space-y-2">
          {result.reasons.map((r, i) => (
            <li key={i} className="flex gap-2 text-slate-700">
              <span className="mt-1 text-slate-400" aria-hidden>
                •
              </span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      )}

      {result.advice && (
        <div className="mt-5 rounded-xl bg-slate-50 p-4">
          <h3 className="text-sm font-semibold text-slate-500">
            {t.whatToDo}
          </h3>
          <p className="mt-1 text-slate-800">{result.advice}</p>
        </div>
      )}

      {result.used_ai && (result.ai_reason || result.ai_advice) && (
        <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
          <h3 className="text-sm font-semibold text-indigo-700">
            {t.aiSecondOpinion}
          </h3>
          {result.ai_reason && (
            <p className="mt-1 text-slate-800">{result.ai_reason}</p>
          )}
          {result.ai_advice && (
            <p className="mt-2 text-slate-700">{result.ai_advice}</p>
          )}
          {result.ai_tools.length > 0 && (
            <p className="mt-3 text-xs text-indigo-600">
              {t.toolsUsed}: {result.ai_tools.join(", ")}
            </p>
          )}
        </div>
      )}

      {result.child_message && (
        <div className="mt-5 rounded-xl bg-slate-50 p-4">
          <h3 className="text-sm font-semibold text-slate-500">
            {t.childMessage}
          </h3>
          <p className="mt-1 whitespace-pre-line text-slate-800">
            {result.child_message}
          </p>
        </div>
      )}

      {result.risk === "danger" && result.emergency_number && (
        <p className="mt-5 text-sm text-red-700">
          {t.emergency}:{" "}
          <span className="font-semibold">{result.emergency_number}</span>
        </p>
      )}
    </section>
  );
}
