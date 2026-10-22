# frontend/

The Next.js (App Router) + TypeScript + Tailwind + shadcn/ui web app. Scaffolded in **Phase 1, step 6**.

Planned layout:

| Path | What lives here |
| --- | --- |
| `app/` | Pages (routes): `/` chat, `/knowledge`, `/graph`, `/analytics`, `/settings` |
| `components/` | UI components, one per file: chat, agent panel (Phase 4–5), approval card (Phase 4), charts (Phase 3/7) |
| `lib/events.ts` | TypeScript mirror of the backend `StreamEvent` types. **Must match `backend/core/events.py` exactly.** |
| `lib/` | API client, the SSE stream hook, small utilities |
