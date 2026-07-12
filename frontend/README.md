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

## Structure

- `app/page.tsx` — the check form + result, a single client component.
- `components/ResultCard.tsx` — renders the verdict (risk badge, reasons,
  advice, AI second opinion, forward-to-family note).
- `lib/api.ts` — typed `fetch` wrapper for `POST /api/check`.
- `lib/types.ts` — request/response types mirroring the API contract.
- `lib/i18n.ts` — zh/en UI strings and risk-colour styles.

## Build

```bash
npm run build
```
