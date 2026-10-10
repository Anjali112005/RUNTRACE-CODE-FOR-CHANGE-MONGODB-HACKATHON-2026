# RunTrace dashboard

React 18 + TypeScript + Vite + Tailwind CSS, with React Router, TanStack Query, Recharts, Lucide icons,
React Hook Form and Zod.

## Run (Windows PowerShell)

```powershell
cd frontend
npm install
Copy-Item .env.example .env      # VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev                      # http://127.0.0.1:5173
```

* `VITE_PORT` sets the dev port; if it is busy Vite moves to the next free port (`strictPort: false`).
  Add whatever origin Vite prints to `RUNTRACE_CORS_ORIGINS` in `backend/.env`.
* `npm run build` type-checks and builds to `dist/`; `npm run preview` serves the build.
* `npm test` runs the Vitest + Testing Library suite (`src/test/`), with `fetch` mocked — no backend needed.

## Structure

```
src/
  api/          typed fetch client (ApiError, in-memory admin token) + endpoint functions
  hooks/        TanStack Query hooks (queries, mutations, cache invalidation)
  types/        API types mirroring the backend schemas
  contexts/     ThemeContext (light default, dark toggle, persisted)
  layouts/      AppLayout: sidebar, mobile drawer, breadcrumbs, connection status, theme toggle
  components/   UI kit (cards, stat strip, CTA, badges, empty/error/loading states, code/JSON views),
                RunList, EventTimeline, FindingView (evidence, verify, AI), KeyReveal, ActivityChart
  pages/        Overview, Projects, ProjectDetail, Runs, RunDetail, Compare, Findings, Metrics,
                SDK & Integration, Settings, NotFound
  styles/       design tokens (CSS variables) + Tailwind component classes
  test/         Vitest setup, helpers and tests
```

## Design

The visual language follows the supplied reference: white surfaces, black text and 1.5px black outlines,
`#FFC400` accent blocks, bold condensed headings (Barlow Condensed), Inter body text, JetBrains Mono for IDs
and JSON, bordered stat strips with dividers, list cards with a small "route" marker, and yellow call-to-action
bars with a black arrow block. All colours are CSS variables in `src/styles/index.css`; `.dark` on `<html>`
switches to the dark palette (`#111214` / `#1C1F24` / `#30343B` / `#F5F6F8`).

## Data rules

* Every page reads live API data; failures show an error with a hint and never fall back to fake data.
* Demo records are labelled with a **Demo** badge and can be filtered out (Runs, Metrics).
* API keys are displayed only in the one-time reveal panel (component state); the optional admin token is kept
  in memory. Nothing secret is written to localStorage, sessionStorage or cookies — only the theme choice is.
