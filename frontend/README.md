# Parent Check — Web Frontend

A [Next.js](https://nextjs.org/) (App Router) + TypeScript + Tailwind CSS frontend
for the 爸妈求证 (Parent Check) scam-safety agent. It talks to the Flask backend's
JSON API (`POST /api/check`) instead of the server-rendered templates, so the
analysis pipeline (rule engine → LangGraph AI second opinion) is decoupled from
the UI.

## Run it

The backend must be running first (see the repo root README — `docker compose up`
serves it on `http://localhost:8000`).

```bash
cd frontend
npm install
cp .env.local.example .env.local   # adjust NEXT_PUBLIC_API_BASE if needed
npm run dev                        # http://localhost:3000
```

The backend allows this origin via CORS (`FRONTEND_ORIGIN`, defaults to
`http://localhost:3000`).

For a hosted frontend, set `NEXT_PUBLIC_API_BASE` to the public HTTPS Flask
origin **before building**, and allow the frontend's origin in Flask. Never
put keys in `NEXT_PUBLIC_*` values. This frontend uses the stateless API and
does not save history; the Flask HTML frontend offers per-browser history.
Changing language clears the old localized result so a new check is explicit.

## Structure

- `app/page.tsx` — the check form (paste text / a link, or upload a screenshot)
  + result, a single client component.
- `components/ResultCard.tsx` — renders the verdict (risk badge, reasons,
  advice, AI second opinion, forward-to-family note).
- `lib/api.ts` — typed `fetch` wrappers for `POST /api/check` and
  `POST /api/check-image`.
- `lib/types.ts` — request/response types mirroring the API contract.
- `lib/i18n.ts` — zh/en UI strings and risk-colour styles.

## Build

```bash
npm run build
```

Run `npm test` for response-schema/rendering regressions and `npm audit` for
the locked dependency graph. Next.js uses the patched 15.5 maintenance release;
the PostCSS override keeps its compatible 8.x dependency on a patched version.
