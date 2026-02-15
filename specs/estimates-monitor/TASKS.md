TASKS.md — Implementation tasks (updated 2026-02-15)

Status legend: [x] done, [~] partially done, [ ] not started

Phase 1: Schedule detection + PDF download (DONE)
- [x] Python package skeleton (`estimates_monitor`) with modules
- [x] `storage.py` — state.json read/write helpers (seen, posted, mark_seen, update_seen, is_posted, mark_posted)
- [x] `schedule.py` — parse APH schedule HTML, select latest "Published in full" by ref_no descending
- [x] `parlinfo.py` — extract PDF URL from ParlInfo display page HTML (prefer toc_pdf)
- [x] `fetcher.py` — removed (unused; all fetching via schedule.py and downloader.py)
- [x] `downloader.py` — deterministic PDF download via requests with content-hash naming
- [x] `cli.py` — CLI commands: `latest`, `latest --absolute`, `resolve-pdf <url>`, `download-latest`
- [x] Tests: schedule parsing, ordering, committee fallback, PDF link extraction, storage, downloader 403 handling
- [x] Remove Playwright from Python library (browser WAF bypass moved to OpenClaw agent)

Phase 2: Text extraction + summarisation
- [x] `parser.py` — MarkItDown PDF text extraction (validated against real 1.5MB transcript)
- [x] `summarizer.py` — map-reduce LLM summarisation to X thread JSON (prompts externalised to `prompts/*.md`, thread validation added)
- [x] Install `markitdown` and validate extraction against a real Senate Estimates transcript PDF
- [x] Tune summarisation prompts for Australian political context (committee names, senator names, department names)
- [x] Add thread length validation (each tweet ≤ 280 chars, thread ≤ 8 tweets)
- [x] Test: summariser with mock LLM returns valid thread JSON structure

Phase 3: Pending thread store + approval gate (DONE)
- [x] Create `data/pending/` directory structure (auto-created by `pending.py`)
- [x] Implement pending store: `pending.py` — save/load/list threads as `data/pending/<thread_id>.json` with full metadata
- [x] Implement status transitions: pending → approved → published / failed (with retry: failed → approved)
- [x] CLI commands: `status [--filter]`, `approve <thread_id> [--dry-run]`, `reject <thread_id>`
- [x] Dry-run mode: output exact per-tweet payloads (text, chars, reply_to) without changing status
- [x] Test: 16 tests covering save/load, list/filter, all transitions, terminal states, invalid transitions, CLI commands, dry-run

Phase 4: X API publishing (DONE)
- [x] Implement `x_client.py` with mockable `create_post(text, reply_to_id=None)` and `create_thread(tweets[])`
- [x] Thread creation: root post → reply chain with correct `reply_to_id` threading
- [x] Record published post IDs in pending store and `state.json` via `mark_posted()`
- [x] Handle mid-thread failure: record last successful post, allow `approve` to resume from where it left off
- [x] Idempotency: skip publish if already published
- [x] OAuth1 credential management (env vars: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`) via `make_post_func()`
- [x] CLI command: `publish <thread_id>`
- [x] Test: 10 tests — mock X client, thread creation, reply chain, partial failure + resume, idempotency, CLI publish

Phase 5: OpenClaw agent integration (DONE)
- [x] Create workspace skill: `skills/estimates-monitor/SKILL.md`
  - AgentSkills-compatible frontmatter (name, description, metadata with requires.env for X API keys)
  - Instructions covering full pipeline: check schedule → download PDF (or browser fallback on 403) → extract text → summarise → save pending thread → announce for approval
  - Browser fallback flow: agent detects `parlinfo_blocked` from CLI JSON → uses `browser` tool to navigate ParlInfo → downloads PDF → registers via `--register-pdf`
  - Approval flow: user says "approve" → agent runs `approve` + `publish` commands
  - CLI command reference for all subcommands the agent needs
- [x] Create handover document: `OPENCLAW_SETUP.md` — full setup instructions for OpenClaw agent (venv, credentials, cron job, troubleshooting)
- [ ] Configure skill env injection in `openclaw.json`: `skills.entries.estimates-monitor.env` for X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET (user action — requires X API credentials on OpenClaw machine)
- [ ] Create cron job on OpenClaw machine (user action — run command from OPENCLAW_SETUP.md)
- [ ] Test cron job fires and agent completes pipeline end-to-end (manual verification)

Phase 6: Robustness + polish
- [ ] Add structured logging throughout pipeline
- [ ] Rate limiting for ParlInfo requests (respect retry-after headers)
- [ ] PDF size/validity checks before extraction
- [ ] PDF retention policy (configurable max age/count)
- [ ] Graceful handling of schedule page changes (new URL patterns, table structure changes)
- [ ] Error reporting: agent announces failures with actionable detail (which step failed, what to do)

Tests summary
- [x] 54 existing tests (all passing): schedule, downloader, storage, CLI, summariser, pending store, X client
- [x] Phase 2 tests: MarkItDown extraction, summariser prompt/output validation
- [x] Phase 3 tests: pending store CRUD, approval state machine, CLI status/approve/reject/dry-run
- [x] Phase 4 tests: X client mock, thread creation, reply chain, partial failure + resume, idempotency
- [ ] Manual E2E: cron job → schedule check → download → extract → summarise → approve → publish

Dev notes
- Python 3.13.7 venv at `.venv/`
- Dependencies: `requests`, `requests-oauthlib`, `beautifulsoup4`, `pytest`, `markitdown[all]`, `python-dotenv` (all in `requirements.txt`).
- No `playwright` dependency in Python — browser automation is at the OpenClaw layer.
- All JSON output from CLI commands for agent consumption.
