Plan: Implementation approach and decisions

0) Research / recon (completed)
- Confirmed APH schedule page has NO WAF — `requests` works fine.
- Confirmed ParlInfo pages return HTTP 403 with Azure WAF JS Challenge to non-browser clients.
- Confirmed OpenClaw's `browser` tool (managed `openclaw` Chrome profile, headed, CDP + Playwright under the hood) can bypass WAF.
- Confirmed OpenClaw's `cron` tool supports recurring isolated agent turns with delivery to any chat channel.
- Decision: Python library stays requests-only; browser WAF bypass is handled at the OpenClaw orchestration layer.

Architecture: two-layer design

Layer 1 — Python library (`estimates_monitor`)
- Pure data pipeline: schedule parsing, PDF URL resolution, deterministic HTTP download, text extraction, summarisation, state management.
- No browser automation, no Playwright dependency.
- Commands output structured JSON for the agent to consume.
- On 403 from ParlInfo, raises an error — the agent handles the browser fallback.

Layer 2 — OpenClaw agent (cron job)
- Orchestrates the full pipeline via tool calls:
  1. `exec` → `python -m estimates_monitor.cli latest --json` — check for new transcripts.
  2. If new: `exec` → `python -m estimates_monitor.cli download-latest --json` — attempt HTTP download.
  3. If download fails (403): `browser open <parlinfo_url>` → `browser wait --load networkidle` → `browser download <ref> <filename>` — WAF bypass via OpenClaw's managed browser.
  4. `exec` → text extraction (MarkItDown on downloaded PDF).
  5. Agent performs summarisation (LLM call) to produce an X thread draft.
  6. Saves draft to `data/pending/<thread_id>.json`.
  7. Announces to user's chat for approval.
  8. On approval: publishes thread via X API.
- The agent can reason about errors and adapt (retry, try different URL, report failure).

OpenClaw cron job setup
- Schedule: daily at 8am AEST (`0 8 * * *`, tz `Australia/Sydney`).
- Session: `isolated` (dedicated agent turn, no main chat clutter).
- Delivery: `announce` to configured channel (WhatsApp/Telegram/etc).
- The agent gets a prompt like: "Check for new Senate Estimates transcripts. If found, download the PDF, extract text, generate an X thread draft, and announce for approval."
- Exponential retry backoff on failure (30s → 1m → 5m → 15m → 60m).

ParlInfo WAF strategy
- Primary: Python `requests` — works when ParlInfo serves content without WAF (varies by time/IP/cookies).
- On 403: OpenClaw agent's `browser` tool navigates to the page in the managed `openclaw` Chrome profile. The profile persists cookies/storage across sessions, so the WAF JS challenge typically resolves automatically after the first pass.
- No `parlinfo-setup` manual step needed — the OpenClaw browser handles WAF transparently.
- If WAF behaviour changes (e.g., CAPTCHA added), the agent reports failure and the user can intervene via the browser tool manually.

Schedule parsing (implemented)
- Fetch APH schedule page via `requests` (no WAF on this page).
- Resilient to URL changes: tries `SCHEDULE_URL_CANDIDATES` in order, skips APH 404 helper pages.
- Parse HTML table rows → `TranscriptEntry` dataclass with ref_no, title, page_url, published_date, status, committee_url.
- Sort by ref_no descending (date as fallback) to select the latest "Published in full" entry.
- On ParlInfo display page 403, falls back to committee page for PDF link resolution.

PDF download (implemented)
- `download_pdf_deterministic()`: requests streaming with content-hash naming (`<slug>_<sha256[:8]>.pdf`).
- Raises on 403 — agent handles browser fallback at orchestration layer.
- Fragment stripping on URLs (`;fileType=...#search=...` patterns on ParlInfo links).

Text extraction (implemented — needs validation)
- `parser.extract_text_with_markitdown()`: MarkItDown Python API preferred, CLI fallback.
- Injectable for tests.

Summarisation (implemented — needs prompt tuning)
- `summarizer.summarise_pipeline()`: map-reduce chunking.
  - Map: chunk transcript text → per-section bullet summaries.
  - Reduce: combine section summaries → structured X thread (JSON: `{"tweets": [{"text": "..."}], "notes": "..."}`).
- LLM call is injected (function parameter) for testability.
- Prompts produce a 6–8 tweet thread: headline → key points with stakeholders → notable quotes → PDF link.

Pending thread store (to implement)
- Save generated threads to `data/pending/<thread_id>.json`.
- Fields: `thread_id` (UUID), `transcript_id` (page_url), `title`, `pdf_url`, `tweets[]`, `status` (pending/approved/published/failed), `created_at`, `published_post_ids[]`.
- The agent announces thread drafts for user review.

Approval gate (to implement)
- User reviews the draft (delivered via chat announce or pending store inspection).
- Explicit approval triggers publish. No automatic posting.
- Dry-run mode shows exact per-tweet payloads without sending API requests.

X API publishing (to implement)
- `x_client.py`: mockable client with `create_post(text, reply_to_id=None)`.
- Thread creation: post root tweet, then reply chain.
- Record published post IDs in pending store and `state.json`.
- On mid-thread failure: record partial state, allow resume on retry.
- Idempotency: check `state.json` before publishing; skip if already posted.

State management (implemented)
- `data/state.json`: tracks `seen` (discovery + download metadata) and `posted` (X publish metadata).
- Atomic writes via temp file + rename.
- Functions: `mark_seen`, `update_seen`, `get_seen`, `is_seen`, `is_posted`, `mark_posted`.

Failure modes and recovery
- Schedule page 502/timeout: retry with deadline (already implemented in `_fetch_schedule`).
- ParlInfo 403: Python raises; agent uses browser tool (cron retries with backoff).
- PDF not valid (`%PDF` check fails): agent reports error, does not proceed to extraction.
- LLM failure: agent retries or reports.
- X API failure mid-thread: partial state recorded; approve resumes from last successful post.

Data model
- `TranscriptEntry`: title, page_url, pdf_url, published_date, status, committee_url, ref_no, pdf_fallback_committee.
- `state.json`: `{seen: {<page_url>: {...}}, posted: {<page_url>: {...}}}`.
- `data/pending/<thread_id>.json`: `{thread_id, transcript_id, title, pdf_url, tweets[], status, created_at, ...}`.

Dependencies (Python)
- `requests`, `beautifulsoup4`, `pytest` (dev) — currently installed.
- `markitdown` — for PDF text extraction (to install).
- `openai` or direct HTTP — for LLM summarisation (to install/configure).
- `tweepy` or direct HTTP — for X API publishing (to install/configure).
- NO `playwright` in Python.

Security
- X API credentials: stored as environment variables or OpenClaw secrets, never in repo.
- State/pending files: local only, `.gitignore`d.
- No profile data to manage (OpenClaw browser handles its own profile).
