# knowledge.md — SmartLog AI

> Read this file at the start of EVERY session. Update the Progress section after every phase.

---

## Project summary

**SmartLog AI: Intelligent Incident Classification using Hybrid AI for Enterprise Log Monitoring**
College Experiential Learning project at **RV College of Engineering (RVCE), EL Phase I**.

Classifies enterprise logs (CRM, HRMS, billing, cloud/server) into incident categories in
real time, detects unknown anomalies, and shows everything in an ops-style dashboard.
The classifier is a **hybrid pipeline** where each stage can short-circuit:
regex rules → Sentence-BERT + Logistic Regression → DBSCAN anomaly detection →
Claude LLM fallback, degrading gracefully at every step.

---

## Fixed stack (do not change)

| Layer     | Tech |
|-----------|------|
| Frontend  | React + TypeScript + Vite + Tailwind + shadcn/ui + Recharts + React Router + TanStack Query + lucide-react |
| Backend   | FastAPI (Python 3.10+), SQLAlchemy + SQLite, WebSockets |
| ML        | sentence-transformers (`all-MiniLM-L6-v2`), scikit-learn (LogisticRegression, DBSCAN, PCA), joblib, regex |
| LLM       | Anthropic Claude API, key from `ANTHROPIC_API_KEY` env var (missing key ⇒ graceful "Unknown" fallback, never crash) |

Env: frontend `.env.local` with `VITE_API_URL` (default `http://localhost:8000`) and
`VITE_USE_MOCK` (default `false`, keep a mock fallback). Backend `.env` for secrets —
never printed or committed (`.env.example` only).

---

## Pipeline (each stage can short-circuit)

1. **Preprocess** — strip timestamps, IDs, IPs, hex, numbers, symbols; lowercase;
   normalize whitespace. Returns `cleaned_text`.
2. **Regex classifier** — known patterns → category with high confidence.
   If matched, return immediately (`classified_by: "Regex"`).
3. **Sentence-BERT embeddings + Logistic Regression** — for known categories.
   If max probability ≥ **0.70**, return (`classified_by: "BERT+LogReg"`).
4. **DBSCAN** — on embeddings of low-confidence logs; noise points = unknown
   anomalies; clusters them for the Anomaly Explorer (`classified_by: "DBSCAN"`).
5. **LLM few-shot fallback (Claude API)** — returns strict JSON
   `{category, severity, explanation, remediation}`. Missing key or failed call ⇒
   degrade to category "Unknown" with low confidence. **Never crash.**

Models load **once at FastAPI startup (lifespan)**, never per request.

### Categories

Database Error, API Failure, Login Failure, Payment Issue, Security Alert,
Resource Usage, Workflow Error, User Action, Unknown.

### Severity

Critical, High, Medium, Low — derived from category + log level + keywords.

### Classification result contract (per log)

`category`, `severity`, `confidence`, `classified_by` (`"Regex" | "BERT+LogReg" | "DBSCAN" | "LLM"`),
`cleaned_text`, `is_known`, `pipeline_trace` ([`{stage, matched, score}`]),
`explanation`, `remediation`.

---

## Training

- `backend/train.py` generates ~2000 labeled synthetic rows of realistic
  CRM/HRMS/billing/cloud/server logs across all categories with varied wording;
  also loads LogHub CSVs from `backend/data/` when present.
- 80/20 stratified split; train LogisticRegression on embeddings; print and **save**
  accuracy, per-class precision/recall/F1, confusion matrix → `backend/models/metrics.json`.
- Save baseline comparison: rule-based only vs ML only vs Hybrid (F1 + false-alert rate).
- Artifacts saved with joblib → `backend/models/`.

---

## Backend tree

```
backend/
  main.py, schemas.py, db.py, config.py
  routers/   incidents.py, classify.py, anomalies.py, metrics.py, upload.py, stream.py
  pipeline/  preprocess.py, regex_classifier.py, embedder.py, classifier.py,
             anomaly.py, llm_fallback.py, pipeline.py
  data/sample_logs.csv   (~500 realistic logs: Hadoop-style + CRM/HRMS/billing/cloud)
  models/, train.py, seed.py, requirements.txt, .env.example, tests/
```

- Pydantic schemas mirror frontend TypeScript types **exactly** (same field names/casing).
- CORS: `http://localhost:5173` and `http://localhost:8080`.
- `seed.py` pre-populates ~300 classified incidents, realistic uneven distributions
  (more Info/Low than Critical, a couple of busy hours, one noisy source).

### API contract summary

| Method & path | Purpose | Notes |
|---|---|---|
| `GET /api/health` | health check | `{status, models_loaded, ...}` |
| `GET /api/dashboard/stats` | KPI strip + chart data | total logs, incidents, critical count, unknown anomalies, avg detection ms, false alert rate, by-category, by-source, by-severity, change vs previous 24h |
| `GET /api/incidents/timeseries` | incidents-over-time line chart | bucketed counts |
| `GET /api/incidents` | incident list | filters: severity, category, source, status, date range, search; pagination; sorting |
| `GET /api/incidents/{id}` | incident detail | raw + normalized log, pipeline trace |
| `PATCH /api/incidents/{id}/status` | status workflow | Open / Acknowledged / Resolved |
| `POST /api/classify` | classify one log | body `{text}` → full classification contract |
| `POST /api/upload` | batch classify `.log/.txt/.csv` | background task with progress; results stored |
| `GET /api/anomalies/clusters` | DBSCAN scatter data | 2D PCA points + cluster ids + noise flag + sample logs |
| `POST /api/anomalies/clusters/{id}/label` | human feedback | saved as a training example |
| `GET /api/metrics` | model metrics | serves real saved `metrics.json` |
| `WS /ws/stream` | live log stream | replays `sample_logs.csv` at random 1–3s intervals, classifies each through the REAL pipeline, stores it, broadcasts JSON |

---

## Frontend pages

1. Dashboard — stat strip, incidents-over-time line chart, category breakdown
   (horizontal bars, NOT a donut), source bar, severity distribution, compact live feed.
2. Live Monitor — log viewer table (timestamp, source, level, message, category,
   severity dot, confidence, classified-by), pause/resume, filters, search; row click
   opens detail drawer. Real log viewer: mono, one line per event, only the level token
   colored, auto-scroll with "Jump to latest" when scrolled up, 120 ms fade-in.
3. Classify log (demo) — textarea + 6 clickable example logs; pipeline stepper;
   category, severity, confidence bar, cleaned text, known vs unknown, explanation,
   remediation. Stepper: horizontal numbered steps joined by a thin line; deciding
   stage filled with accent; skipped stages muted with "Skipped"; score in mono.
4. Incidents — sortable/paginated/filterable table, CSV export, status workflow,
   detail drawer (raw + normalized log, related-logs timeline, probable root cause,
   remediation steps).
5. Anomaly explorer — DBSCAN scatter + side list of unknown clusters + "Label cluster"
   dialog.
6. Model performance — accuracy/precision/recall/F1 strip, confusion matrix,
   per-class table, Rule-based vs ML vs Hybrid comparison, classifier usage breakdown.
7. Upload logs — drag-and-drop, preview, progress bar, results summary linking to Incidents.
8. About — project title, flat SVG pipeline diagram in the palette, tech list as plain
   text, RVCE credit.

All data access via `src/lib/api.ts` + TanStack Query hooks in `src/hooks/`.
WebSocket client auto-reconnects. Every call has loading, empty and error states.
Confusion matrix: single-hue teal intensity, values shown. Anomaly scatter: 5 px dots,
known clusters muted teal/grey, noise in violet, thin axes, light grid.

---

## DESIGN BRIEF (critical)

**Feel:** calm, dense, precise, understated internal ops tool (Sentry, Linear, Grafana).

### HARD BANS

- No purple/blue/pink gradients anywhere. No glassmorphism, blur, glow, neon,
  heavy shadows, mesh/blob backgrounds, gradient text.
- No emoji, no sparkle/magic-wand icons, no "AI-powered" badges, no robot imagery.
- No icons inside colored circles/squares on KPI cards.
- No hero sections, marketing copy, "Welcome back!", or exclamation marks in UI text.
- No giant border radius, no pill-shaped everything.
- No lorem ipsum, no suspiciously round fake numbers; believable uneven ones
  (18,342 logs, 47 incidents, 3 critical, 92.7% F1).

### Typography

- **IBM Plex Sans** for UI, **IBM Plex Mono** for logs, IDs, timestamps, numeric cells
  (Google Fonts). Do NOT use Inter or system-ui as primary font.
- Sizes: 11 px (table headers, uppercase, slight letter-spacing), 12 px (meta/table),
  13 px (dense body), 14 px (default), 16 px (section titles), 24 px (page titles).
  Weights 400/500/600 only. Sentence case everywhere. `tabular-nums` on all figures.

### Color

Tokens in `src/index.css` CSS variables and `tailwind.config`; never hard-code colors
in components. Never edit `src/components/ui/*` primitives except theme tokens in CSS vars.

- **Light:** bg `#FAFAF8`, surface `#FFFFFF`, subtle `#F4F3EF`, border `#E7E5E0`,
  text `#1C1B1A`, muted `#6B6862`.
- **Dark (secondary):** bg `#141413`, surface `#1B1B1A`, subtle `#222221`,
  border `#2E2D2B`, text `#ECEAE6`, muted `#9A968E` (neutral charcoal, NOT navy).
- **Accent:** deep teal `#0F766E` (dark `#2DD4BF`, slightly desaturated) — primary
  buttons, active nav, links, focus rings only.
- **Severity** (small dots or soft-tint badges, never big filled blocks):
  Critical `#B42318`, High `#C2410C`, Medium `#A16207`, Low `#475569`,
  Unknown anomaly `#6D5BA8` (reserved for unknown anomalies only).
  Badge = 1 px border + very light tint + dark same-hue text.
- **Charts:** teal shades + neutral greys; severity colors only where severity is
  encoded. No rainbow.

### Layout and shape

- 4 px spacing grid; content max-width **1280 px**; tight vertical rhythm in tables.
- Radius: 6 px cards/inputs/buttons, 4 px badges.
- Regions separated by 1 px borders + whitespace, not shadows. Only popovers/drawers
  get a faint shadow: `0 1px 2px rgba(0,0,0,0.04)`.
- Fixed left sidebar **232 px**: text labels with 16 px lucide line icons (1.5 stroke);
  active = subtle background + accent text. Wordmark "SmartLog" semibold + small mono
  "AI". Footer: muted "RV College of Engineering · EL Phase I".
- Top bar: page title left; right side only "● Streaming" (6 px green dot) + theme toggle.

### Components

- KPI area: one bordered **stat strip** divided by vertical hairlines — muted label,
  24 px tabular number, tiny muted delta ("▲ 12 since yesterday"). No icons, not four
  identical cards.
- Tables are the hero: 36 px rows, sticky header, no zebra, subtle hover, severity as
  a 6 px dot, mono timestamps/log text with ellipsis, right-aligned numbers.
- Drawers: from the right, 480 px, small section headings, key-value rows, raw log in
  a bordered mono block with a Copy button.
- Buttons: primary solid accent, secondary white with border, ghost for toolbars;
  32 px high, 13 px text.
- Toasts: small, bottom-right, plain text. Motion: only 100–150 ms opacity/translate;
  skeleton loaders flat grey, no shimmer.

### Microcopy (write like a person on an ops team)

Short and specific: "No incidents match these filters." / "Paused. 14 new events
waiting." / "Couldn't reach the backend. Retrying in 5s." / "Classified by regex rule
db_timeout_01 in 3 ms."
Empty states: one line plus one text-link action, no illustrations.
Never use "Unlock insights", "Supercharge", "Seamless", "Harness the power of AI",
"Leverage".

### Realism

- Logs look real: varied timestamps, hostnames (`crm-app-03`, `billing-api-02`),
  request IDs, user IDs, stack-trace fragments, mixed levels.
- Seed data uneven: more Info/Low than Critical, a couple of busy hours, one noisy
  source system.

---

## Run commands (document in README at Phase 9)

```
backend:  python -m venv venv && pip install -r requirements.txt && python train.py && python seed.py && uvicorn main:app --reload
frontend: npm install && npm run dev
```

---

## Progress

- **Phase 0 — DONE.** Repo explored: only `readme.md` exists (no /frontend, no
  /ml_code → build both from scratch). `knowledge.md` created. Frontend-expected API
  function table emitted (see session output).
- **Phase 1 — DONE.** Backend skeleton live and verified. `backend/`:
  `main.py` (lifespan + CORS 5173/8080), `config.py`, `db.py`
  (Incident/UploadedFile/TrainingExample tables), `schemas.py` (Pydantic mirror
  of the TS contract), `pipeline/preprocess.py` + `regex_classifier.py`
  (real, reusable; 9 rules), `pipeline/pipeline.py` (Preprocess→Regex real,
  ML/LLM stages stubbed for Phase 3), and routers `incidents.py`
  (stats+list+detail+status+timeseries), `classify.py` (`/api/classify`,
  `/api/classify/store`), `anomalies.py` (stub scatter + label endpoint),
  `metrics.py` (placeholder until metrics.json), `upload.py` (background
  processing + status poll), `stream.py` (WS hello + 2s sample replay until
  Phase 4). Pinned `requirements.txt`, `.env.example`. All endpoints verified
  with curl incl. filters, PATCH workflow, upload progress and WS frames.
  `smartlog.db`/`server.log` test artifacts removed after verification.
- **Phase 2 — DONE.** Frontend built from scratch in `frontend/` (Vite + React +
  TS, Tailwind 3.4, TanStack Query v5, React Router, Recharts, lucide-react +
  radix dialog/select deps). `src/types/index.ts` mirrors `backend/schemas.py`
  exactly. `src/lib/api.ts` = typed client for ALL endpoints + `ApiError`;
  `src/lib/ws.ts` = auto-reconnecting WS (exponential backoff, cap 15 s);
  `src/lib/mock.ts` = offline fallback behind `VITE_USE_MOCK`;
  `.env.local` (`VITE_API_URL=http://localhost:8000`, `VITE_USE_MOCK=false`).
  `src/hooks/useApi.ts` = all query/mutation hooks (stats, timeseries,
  incidents+filters, incident, status, classify, upload+progress polling,
  clusters, label-cluster, metrics, live stream buffer with pause).
  UI primitives in `src/components/ui/` (button.tsx + primitives.tsx: card,
  table, badge, severity dot, drawer, inputs, skeleton, progress) — Phase 5
  restyles via CSS vars, structure stays. All 8 pages functional with
  loading/empty/error states: Dashboard, Live, Classify, Incidents, Anomaly,
  Performance, Upload, About. `npm run build` passes (`tsc -b` type-checks
  the schema mirror). Verified: backend + Vite dev server both up, CORS
  preflight from :5173 passes, index serves.
- **Phase 3 — DONE.** Real hybrid pipeline live. New files:
  `pipeline/embedder.py` (all-MiniLM-L6-v2, loads at startup),
  `pipeline/classifier.py` (LogReg head artifact), `pipeline/anomaly.py`
  (DBSCAN nearest-fitted-point membership + 2D PCA),
  `pipeline/llm_fallback.py` (Claude few-shot, strict JSON,degrades on
  missing key/timeout/bad JSON — never crashes), `train.py` (2000 synthetic
  rows incl. distractor/collider noise rows, optional LogHub CSV loader,
  80/20 stratified split, baselines Rule vs ML vs Hybrid). Artifacts saved:
  `models/bert_logreg.joblib`, `models/dbscan.joblib`, `models/pca.joblib`,
  `models/metrics.json` (ip_reminder note: metrics only, no copyrighted
  text). Training printed: LogReg head 100% on test split (synthetic
  templates repeat), Hybrid macro F1 0.9446, Rule-based only F1 0.762 /
  false-alert 0.070, ML only F1 1.0 / 0.003, Hybrid F1 0.945 / 0.010,
  DBSCAN 2 clusters + 15 noise on 61 low-confidence embeddings. LLM degrades
  to Unknown with classified_by=LLM when ANTHROPIC_API_KEY is unset (current
  state — key not configured). Fixed during phase: missing DATA_DIR config,
  `_fill` label/template mismatch, `y_mlonly` desync from `continue`,
  KeyError 'cleaned', trace not attached to results, deciding-stage `matched`
  flags. Verified via curl: health shows models_loaded=true after lifespan;
  regex short-circuit (Database Error/Critical/0.97 via db_timeout_01);
  BERT+LogReg on semantic text (API Failure/0.9251); gibberish → Unknown via
  LLM-degradepath with is_known=false; /api/metrics serves real metrics.json.
  Note for train quality: ML-only baseline equals 1.0 on this synthetic set
  because wording repeats; real LogHub data would lower it.
- **Phase 4 — DONE.** Streaming WebSocket, upload, seed, stats from real DB.
  Created/changed: `backend/data/sample_logs.csv` (~500 realistic logs),
  `backend/routers/stream.py` (replays CSV at random 1-3s, classifies via real pipeline,
  stores to DB, broadcasts), `backend/seed.py` (~300 incidents with uneven distributions
  - more Info/Low than Critical, busy hours, noisy Cloud/Server source), uploaded
  logic already uses real pipeline; stats/timeseries computed from real DB.
  Verified: seeded DB (300 incidents), dashboard stats from real data, timeseries
  endpoint OK, health/models loaded OK.
- Phase 5 — pending. Phase 6 — pending. Phase 7 — pending.
  Phase 8 — pending. Phase 9 — pending.

## readmephase3.md (Dashboard zero state + web scrape) — in progress
- **Phase 0 — DONE (explore only, no edits).** Read `frontend/src/lib/api.ts`,
  `frontend/src/hooks/useApi.ts` (the hooks file; there is no use-smartlog.ts),
  `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/Upload.tsx`,
  `frontend/src/lib/mock.ts`, `backend/main.py`, `backend/seed.py`,
  `backend/config.py`, and routers `upload.py` / `incidents.py` (dashboard stats
  + timeseries live here) / `stream.py` / `anomalies.py` / `metrics.py`.
  Findings: (a) synthetic/mock paths to Dashboard — `seed.py` (~300 rows, doc'd
  as a startup step but run manually; existing smartlog.db still holds its rows),
  `stream.py` synthetic generator replaying `sample_logs.csv` into DB + WS,
  `demo` stub clusters in `anomalies.py` (hardcoded deterministic points),
  mock.ts store (23 canned incidents, fabricated stats 18342/47, upload that
  fakes done without adding records). (b) upload ingest path — `_read_lines` →
  413/422 guards → `UploadedFile` row → background `_process_upload` → per line
  `_guess_source` + level heuristic + `pipeline_orchestrator.classify_text` →
  IncidentRow insert; dashboard fills from DB via /api/dashboard/stats,
  /api/incidents, /api/incidents/timeseries; the upload poller invalidates only
  `incidents` + `stats` queries (missing `timeseries`). (c) Shared ingest plan —
  add `services.ingest_lines(lines, label)` holding the classify+insert+progress
  logic; /api/upload and /api/scrape both call it; WS broadcast via a connection
  registry so ingest pushes ≤50 newest events (Phase 2). Zero state also needs
  `anomalies.py` to return empty clusters from DB on a fresh DB.
- **Phase 1 — DONE.** Zero state. Changed: `backend/routers/stream.py`
  (synthetic generator removed; WS only sends the hello frame and then
  nothing — verified with a websockets client), `backend/seed.py` (argparse
  `--demo` is now required; exits code 2 without it; never run by main.py),
  `backend/reset_data.py` (NEW: deletes incidents + uploads +
  training_examples; confirmation prompt, `--yes` skips),
  `backend/routers/anomalies.py` (stub clusters removed; clusters now computed
  ONLY from unknown incidents in the DB via embedder.embed +
  anomaly_stage.cluster_of/to_2d capped at 200 rows; empty DB -> empty lists;
  falls back to empty lists if models fail), `frontend/src/lib/mock.ts`
  (store rewritten: starts with 0 incidents / baseLogsProcessed=0, stats and
  timeseries computed from the store with all zeros + 0 avg/false-alert, never
  NaN; mock upload actually reads the file and adds parsed rows),
  `frontend/src/pages/Dashboard.tsx` (timeseries chart gets the standard
  EmptyBlock when all 7 day counts are 0; empty messages now "No data yet.
  Upload a log file on the Upload page.", feeds no longer suggest starting
  the stream), `frontend/src/pages/Live.tsx` (empty message no longer
  references sample-log replay). Verified: reset script deleted 5241 incidents
  + 4 uploads → stats/timeseries/incidents/clusters all zero/empty via curl;
  seed gate exit=2; WS hello then silence;  pytest 7 passed; frontend tsc
  clean. Backend serves on :8000 as background process.
- **Phase 2 — DONE.** Fill on ingest. Changed: `backend/services.py` (NEW:
  shared ingest — `run_ingest(upload_id, lines, label)` owns classify +
  IncidentRow insert + chunked progress commits + failed-status handling +
  `_guess_source`/level heuristics moved here; pushes newest ≤50 rows to WS`,
  `backend/routers/stream.py` (connection registry `_clients` +
  `bind_loop()` from main.lifespan + thread-safe `push_incident_frames` via
  `run_coroutine_threadsafe`; dead clients dropped),
  `backend/routers/upload.py` ( Slimmed: parsing + validation only;
  dispatches background to services.run_ingest so /api/scrape can share it),
  `backend/main.py` (binds the event loop for thread->loop pushes),
  `backend/routers/incidents.py` (timeseries window off-by-one fixed: last
  `days` calendar days INCLUDING today — freshly ingested rows always land in
  the last bucket; verified 501 rows counted on today after upload),
  `frontend/src/hooks/useApi.ts` (upload-done invalidation now also covers
  `incidents`, `incident`, `timeseries`, `clusters` — previously missing).
  Verified: upload `data/sample_logs.csv` via /api/upload → 501 incidents,
  dashboard stats filled from DB (total 501 / critical 65 / unknown 118 /
  avg 57.14 ms / 7 categories), feed total 501 with newest id 501, WS client
  received EXACTLY 50 incident frames (ids 452–501), timeseries today = 501;
  then `reset_data.py --yes` back to all zeros; pytest 7 passed.
- **Phase 3 — DONE.** Backend scrape. New: `backend/scraper.py` (extraction
  by content type: text/* → lines, application/json → walk message/msg/log/
  text/line/event + string arrays, text/html → bs4/lxml over pre/code/samp/
  tr/li + id|class contains "log", optional CSS selector, visible-body
  fallback; `log_like_lines` filter = timestamp OR level keyword OR
  http-status/kv pattern, strip, dedupe-adjacent, cap MAX_UPLOAD_LINES),
  `backend/routers/scrape.py` (POST /api/scrape {url, selector?}; 400/422/
  413/502 contract with human details; httpx follow ≤3 redirects, 15 s
  timeout, 5 MB streaming cap, UA SmartLogAI-Scraper/1.0;
  SCRAPE_ALLOW_PRIVATE default true with SSRF guard for public deploys),
  `backend/services.py` shared by both /api/upload and /api/scrape (one
  ingest path), `backend/demo_site/index.html` (~58 mixed CRM/HRMS/billing/
  cloud rows in pre/table/ul incl. 3+ odd unknown lines), `tests/conftest.py`
  (pytest isolation: DATABASE_URL → throwaway sqlite + init_db — the old run
  wrote 6 incidents into smartlog.db; now the dev DB stays clean),
  `tests/test_scrape.py` (14 tests: pre/table/json/plain extraction,
  unknown+hint kept, 400/422 contracts, local-server 202 roundtrip, demo
  page ≥40 valid lines, selector scoping, malformed URLs), config.py added
  MAX_UPLOAD_LINES + SCRAPE_* knobs, requirements.txt += httpx/
  beautifulsoup4/lxml (installed in venv). Verified: pytest 21 passed; curl
  against http.server 9000 — scrape → 202 upload_id=2, 58 lines; bad scheme
  → 400; unreachable port → 502; dev DB reset to zeros after verification.
- **Phase 4 — DONE.** Frontend scrape UI. Changed: `frontend/src/lib/api.ts`
  (`scrapeUrl(url, onProgress?)` reusing the UploadResponse contract; real
  mode POSTs ${BASE_URL}/api/scrape JSON, mock mode rejects with "Fetching
  from a URL needs the backend. Set VITE_USE_MOCK=false."; wired into the
  `api` object unwrapped since it handles mock itself),
  `frontend/src/hooks/useApi.ts` (`useScrapeUrl` mirrors useUpload 1:1:
  UploadProgress state, 500 ms /api/upload/{id}/status polling, same
  query invalidations incl. timeseries+clusters; the URL rides in
  progress.filename so the summary shows the source),
  `frontend/src/pages/Upload.tsx` (tab strip built from the existing Button
  variants — no Tabs component exists in this project — "Upload file" default
  keeps the old flow pixel-identical; "From URL" card with Input placeholder
  http://localhost:9000/logs.html + "Fetch and classify" button; client-side
  validation mirrors the backend 400; errors render in the page's existing
  inline red/muted style — no toast system exists; the shared ProgressSummary
  card is the same markup the file path uses). Verified: tsc clean, Vite
  transforms all three changed modules (200), demo_site (http.server 9000)
  + scrape via the exact request sequence the UI issues → 202/58 lines →
  done → dashboard 58/2/24 + feed total 58; then reset_data.py --yes back
  to zeros. Backend :8000, demo :9000, Vite :5173 running as background
  processes.
- **Phase 5 — DONE.** QA + docs. git diff review: only the intended files
  changed (adds/tweaks above + regenerated __pycache__ and smartlog.db
  artifacts); no component under src/components/ui/*/ touched, no colors/
  fonts/routes changed. Frontend `npm test` does not exist in this project —
  the equivalent checks are `npm run lint` (0 errors, 3 pre-existing style
  warnings incl. a ref read in IncidentDrawer) and `npm run build`
  (tsc -b + vite build, PASSED after fixing two real type bugs I had put in
  mock.ts's count helper: unused generic + unsound casts — replaced with a
  plain countsOf helper mapped into the exact CategoryCount/SourceCount/
  SeverityCount shapes). Backend pytest: 21 passed. Combined-sources
  acceptance verified: 11-row CSV upload + scraped 58 → total_logs 61,
  critical 5, then reset_data.py --yes back to 0. README (root):
  zero-state paragraph, reset_data.py usage, seed.py --demo note, /api/scrape
  contract, scrape limitations (static content only, permission notice), SSRF
  note, demo-site serve command; startup command no longer lists seed.py.
  backend/.env.example: SCRAPE_ALLOW_PRIVATE documented. Final state: fresh
  DB serves all-zero stats with empty lists; WS silent; pytest clean;
  frontend build clean. readmephase3.md acceptance checklist 1-6 all true
  (6 = visual design unchanged, verified by diff + no ui/ component edits).
