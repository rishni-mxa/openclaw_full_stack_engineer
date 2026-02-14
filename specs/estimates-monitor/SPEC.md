Feature: APH Senate Estimates transcript monitor → X thread generation + approval-publish flow

Goal
- Detect newly "Published in full" transcripts from the APH Estimates Transcript Schedule, download the transcript PDF, extract text, summarise into an X (Twitter) thread, and publish after explicit human approval.
- Runs as a daily OpenClaw cron job with no human involvement for the detection + download steps. Human approval is required only before publishing to X.

Architecture overview
- **Python library** (`estimates_monitor`): pure data pipeline — schedule parsing, PDF URL resolution, deterministic download, text extraction, thread generation. No browser automation; uses `requests` only.
- **OpenClaw agent** (cron job): orchestrates the pipeline. Uses `exec` to run the Python library, the `browser` tool to bypass ParlInfo's Azure WAF when needed, and messaging to deliver results / request approval.
- **OpenClaw cron**: daily recurring isolated job that triggers the agent turn automatically.

High-level flow
1. OpenClaw cron fires daily (e.g. 8am AEST).
2. Agent runs `exec` → Python CLI (`latest --json`) to check the APH schedule for new "Published in full" transcripts.
3. If a new transcript is found, the Python CLI returns the ParlInfo display URL and resolved PDF URL.
4. Agent attempts PDF download via Python CLI (`download-latest`). If download fails with 403 (WAF), agent uses its `browser` tool to:
   a. Navigate to ParlInfo display page.
   b. Wait for WAF JS challenge to resolve (`wait --load networkidle`).
   c. Download the PDF (`download` command or `run-code` with `page.waitForEvent('download')`).
5. Agent runs text extraction (MarkItDown) on the downloaded PDF.
6. Agent runs summarisation (map-reduce with LLM) to produce an X thread draft.
7. Draft saved to `data/pending/<thread_id>.json` and agent announces to the user's chat for approval.
8. On explicit approval from the user, agent publishes via X API (thread: root post + replies). Updates state to `published`.

ParlInfo WAF handling
- ParlInfo (parlinfo.aph.gov.au) is protected by an Azure WAF JS Challenge that blocks non-browser clients (HTTP 403).
- The APH schedule page itself has NO WAF — `requests` works fine.
- WAF bypass is handled by the OpenClaw agent's `browser` tool (managed `openclaw` Chrome profile, headed mode, persistent cookies). The Python library does NOT contain any browser automation code.
- The `openclaw` browser profile persists cookies across sessions, so the WAF challenge typically only needs to be solved once per profile.

Non-goals
- Automatic posting without explicit human approval.
- Browser automation inside the Python library (delegated to OpenClaw).
- Playwright as a Python dependency.

Outputs
- Python package `estimates_monitor` with modules: schedule, parlinfo, fetcher, downloader, parser, summarizer, storage, cli
- State tracking via `data/state.json` (seen transcripts, download metadata, published post IDs)
- Pending thread storage under `data/pending/`
- OpenClaw cron job configuration for daily monitoring
- Unit tests + fixtures (schedule HTML, detail HTML, PDF mock)

Constraints & choices
- Stable IDs: Use canonical transcript page URLs as primary keys, generated `thread_id` (UUID) for pending threads.
- PDF downloads: HTTP `requests` only in Python; 403 fallback handled by OpenClaw browser at orchestration layer.
- MarkItDown: Python API preferred; CLI fallback; injectable for tests.
- LLM summarisation: map-reduce chunking with structured JSON output for threads.
- Publishing: X API (OAuth2 user context). If credentials unavailable, threads remain in pending state. Dry-run mode available.
- Safety: Explicit approval gate enforced before any X publishing.
- Dependencies (Python): `requests`, `beautifulsoup4`, `markitdown`, `openai` (or HTTP), `pytest`. No `playwright`.
