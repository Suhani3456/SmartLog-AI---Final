This is an ADDITIVE change to the existing SmartLog AI project (React/TanStack Start frontend + FastAPI backend, already working). Do NOT change the visual design, layout, colors, fonts, routes, or any existing feature. Do NOT touch src/components/ui/\*. Reuse existing components, classes and empty-state patterns. Everything you add must look like it was always part of the app.

Work in the PHASES below, one at a time. After each phase: list files changed, give commands to verify, then STOP until I say "next". Write complete files, no placeholders. Update knowledge.md (Progress section) after each phase. Start with Phase 0.

═══ FEATURE 1: Dashboard starts at zero, fills only after logs are uploaded ═══

Required behaviour

- On a fresh start the Dashboard shows ZERO for every KPI (total logs, incidents, critical, unknown anomalies, avg detection ms, false alert rate), empty charts, and an empty live incident feed.
- Charts and the feed show a small muted empty-state line inside their existing container, e.g. "No data yet. Upload a log file on the Upload page." Reuse the app's existing empty-state style. No new colors, no illustrations.
- The moment a CSV/log upload (or a web scrape, Feature 2) finishes, the Dashboard fills with real values computed ONLY from the ingested logs. Invalidate the existing dashboard/incidents queries so it refreshes automatically, with no manual reload.
- Nothing synthetic may feed the Dashboard any more:
  - Backend: remove the automatic seeding on startup. seed.py must NOT run automatically and must require an explicit --demo flag.
  - Backend: stop the background synthetic log generator. The WebSocket /ws/stream stays connected but emits nothing by default. After an ingest (upload or scrape) it pushes the newly ingested logs, capped at the 50 most recent, so the Live Monitor and the dashboard feed still react.
  - Frontend mock mode (VITE_USE_MOCK=true): the mock store must also start EMPTY (no seeded records, baseLogsProcessed = 0) and fill only when a file is uploaded or a URL is scraped. Keep the existing mock upload logic working.
- Definitions stay exactly as they are today (incident = level != INFO or category Unknown, etc.). When there is no data, every number is 0 and false_alert_rate is 0, never NaN and never a division by zero.
- Uploaded data persists in the SQLite database across page refreshes. Add backend/reset_data.py (a plain script, no UI) that deletes all logs, anomaly clusters and feedback so the app returns to the zero state. Mention it in the README.
- Leave the Model Performance page as it is (those are model evaluation metrics, not upload-dependent). Incidents, Live Monitor and Anomaly Explorer already read from the same data, so they will naturally show only ingested logs; make sure they handle the empty state without errors.

═══ FEATURE 2: Web scrape option (paste a URL, extract logs, classify like a CSV upload) ═══

UI (additive, on the existing Upload Logs page)

- Add a second input option on that page in the same visual style (use the existing Tabs or Card components): "Upload file" (existing, untouched) and "From URL" (new).
- "From URL" has: one URL text input (placeholder "http://localhost:9000/logs.html"), a "Fetch and classify" button, the same progress bar and the SAME results summary component the file upload uses. Show the extracted line count and the source URL in the summary (use the file_name field for the URL).
- Basic client validation: must start with http:// or https://. Errors appear as the existing toast style, for example "Couldn't reach that URL" or "No log-like lines found on that page".

API contract (keep everything going through src/lib/api.ts)

- Add `scrapeUrl(url: string, onProgress?: (pct:number)=>void): Promise<UploadResult>` to src/lib/api.ts (reuse the existing UploadResult type, no new type needed).
- Real mode: POST `${BASE_URL}/api/scrape` with JSON {"url": "..."} and return the UploadResult.
- Mock mode: throw a clear Error("Fetching from a URL needs the backend. Set VITE_USE_MOCK=false.").
- Add a `useScrapeUrl` hook in src/hooks/use-smartlog.ts mirroring `useUploadLogFile` (progress state, same query invalidation, toast on error).

Backend: POST /api/scrape (new router backend/routers/scrape.py)

- Body {url: str, selector?: str}. Accept only http/https. Fetch with httpx: follow at most 3 redirects, 15 s timeout, 5 MB max body, a clear User-Agent ("SmartLogAI-Scraper/1.0"). Localhost, 127.0.0.1 and private network addresses MUST work (that is the main use). Add env var SCRAPE_ALLOW_PRIVATE (default true) and document that it must be set to false if the backend is ever deployed publicly, to prevent SSRF.
- Extraction (backend/scraper.py), by content type:
  - text/plain or similar: split into lines.
  - application/json: walk the structure and collect strings from fields named message, msg, log, text, line, event, or arrays of plain strings.
  - text/html: parse with BeautifulSoup (add beautifulsoup4 and lxml to requirements.txt). Collect text from <pre>, <code>, <samp>, <tr> (join cells with a space), <li>, and any element whose id or class contains "log". If the optional `selector` is given, use only that CSS selector. If nothing is found, fall back to visible body text split by line.
- Keep only log-like lines: a line qualifies if it has a timestamp (ISO, "YYYY-MM-DD HH:MM:SS", syslog-style), OR a level keyword (INFO, WARN, WARNING, ERROR, CRITICAL, FATAL, DEBUG), OR an HTTP status / key=value pattern. Strip whitespace, drop empty and duplicate-adjacent lines, cap at 5000 lines (config.MAX_UPLOAD_LINES).
- Then run EXACTLY the same ingest path the CSV upload uses (the same classify_batch call, the same DB insert, the same source inference, the same UploadResult builder). Refactor the shared part into one function (for example services.ingest_lines(lines, label)) and make BOTH /api/upload and /api/scrape call it, so behaviour cannot drift.
- Errors: 400 for a bad URL, 422 if no log-like lines were found, 502 if the site is unreachable or times out, 413 if the body is too large. Return {"detail": "..."} with a human-readable message the frontend can show.
- Limitation to document in the README: static HTML/text/JSON only. Pages that render logs with JavaScript are not supported. Only scrape sites you own or have permission to scrape.

Test helper

- Create backend/demo_site/index.html: a plain page with about 60 realistic log lines in a <pre> block and a small <table> of log rows (mixed INFO/WARN/ERROR/CRITICAL; CRM, HRMS, billing and cloud style messages; include 3 to 4 odd "unknown" lines). Tell me to serve it with `python -m http.server 9000 --directory backend/demo_site` and scrape http://localhost:9000/index.html.

═══ PHASES (stop after each, wait for "next") ═══
Phase 0: Explore, no edits. Read src/lib/api.ts, src/hooks/use-smartlog.ts, the Dashboard route, the Upload route, the backend routers (upload, dashboard, stream), seed.py, main.py. Report in a short table: (a) every place where mock or seeded or synthetic data reaches the Dashboard, (b) the ingest code path used by /api/upload, (c) your plan for the shared ingest function. Do not edit anything.
Phase 1: Zero state. Remove auto-seed and the synthetic stream generator; make seed.py --demo only; add reset_data.py; make mock store start empty; make stats/timeseries/logs endpoints return zeros and empty lists with no errors. Verify: fresh DB, dashboard shows all zeros and empty states, no console errors on any page.
Phase 2: Fill on ingest. Make the upload path the only thing that populates data; invalidate queries so the dashboard updates right after upload; WebSocket pushes newly ingested logs (max 50). Verify: upload a CSV, then the KPIs, charts and feed fill with real values; run reset_data.py, back to zero.
Phase 3: Backend scrape. Refactor the shared ingest function, add scraper.py and the /api/scrape router, add dependencies, add demo_site. Add pytest tests: HTML with <pre>, HTML table, JSON, plain text, no-log page returns 422, bad URL returns 400. Verify with curl against the demo site.
Phase 4: Frontend scrape UI. Add scrapeUrl in api.ts, the useScrapeUrl hook, and the "From URL" tab on the Upload page, reusing the existing summary component. Verify end to end: serve demo_site on port 9000, paste the URL, results summary appears, dashboard fills.
Phase 5: QA and docs. Confirm no existing feature or style changed (git diff review: only additive changes plus the zero-state edits), existing tests still pass (npm test and pytest), update the backend README (reset script, scrape usage, SSRF note, limitations), update knowledge.md.

Acceptance checklist (all must be true at the end)

1. Fresh start: every Dashboard number is 0, charts and feed show a muted empty message, no errors in the console or the backend log.
2. Upload a CSV: the Dashboard fills automatically; numbers match the Incidents table.
3. Paste http://localhost:9000/index.html on the Upload page: logs are extracted, classified, summarised, and appear on the Dashboard just like a CSV.
4. Both sources combined add up (totals accumulate).
5. reset_data.py returns everything to zero.
6. Visual design, other pages and all existing features are unchanged.

Start with Phase 0 now.
