TASKS.md — Implementation tasks (updated 2026-02-15)

Status legend: [x] done, [~] partially done, [ ] not started

Phase 1: Schedule detection + PDF download (DONE)
- [x] Python package skeleton (`estimates_monitor`) with modules
- [x] `storage.py` — state.json read/write helpers (seen, posted, mark_seen, update_seen, is_posted, mark_posted)
- [x] `schedule.py` — parse APH schedule HTML, select latest "Published in full" by ref_no descending
- [x] `parlinfo.py` — extract PDF URL from ParlInfo display page HTML (prefer toc_pdf)
- [x] `fetcher.py` — requests-only HTML fetch with WAF detection helper
- [x] `downloader.py` — deterministic PDF download via requests with content-hash naming
- [x] `cli.py` — CLI commands: `latest`, `latest --absolute`, `resolve-pdf <url>`, `download-latest`
- [x] Tests: schedule parsing, ordering, committee fallback, PDF link extraction, storage, downloader 403 handling
- [x] Remove Playwright from Python library (browser WAF bypass moved to OpenClaw agent)

Phase 2: Text extraction + summarisation
- [~] `parser.py` — MarkItDown PDF text extraction (implemented, needs validation with real transcript PDF)
- [~] `summarizer.py` — map-reduce LLM summarisation to X thread JSON (implemented, needs prompt tuning)
- [ ] Install `markitdown` and validate extraction against a real Senate Estimates transcript PDF
- [ ] Tune summarisation prompts for Australian political context (committee names, senator names, department names)
- [ ] Add thread length validation (each tweet ≤ 280 chars, thread ≤ 8 tweets)
- [ ] Test: summariser with mock LLM returns valid thread JSON structure

Phase 3: Pending thread store + approval gate
- [ ] Create `data/pending/` directory structure
- [ ] Implement pending store: save thread to `data/pending/<thread_id>.json` with metadata (thread_id, transcript_id, title, pdf_url, tweets[], status, created_at)
- [ ] Implement status transitions: pending → approved → published / failed
- [ ] CLI commands: `status` (list pending/published), `approve <thread_id>` (with --dry-run), `reject <thread_id>`
- [ ] Dry-run mode: output exact per-tweet payloads without API calls
- [ ] Test: approval state transitions, reject, resume from partial failure

Phase 4: X API publishing
- [ ] Implement `x_client.py` with mockable `create_post(text, reply_to_id=None)` and `create_thread(tweets[])`
- [ ] Thread creation: root post → reply chain with correct `reply_to_id` threading
- [ ] Record published post IDs in pending store and `state.json` via `mark_posted()`
- [ ] Handle mid-thread failure: record last successful post, allow `approve` to resume
- [ ] Idempotency: skip publish if `is_posted()` returns True
- [ ] OAuth2 credential management (env vars: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`)
- [ ] Test: mock X client, thread creation, partial failure + resume, idempotency

Phase 5: OpenClaw agent integration
- [ ] Create OpenClaw cron job: daily isolated run at 8am AEST
  ```
  openclaw cron add \
    --name "Estimates transcript check" \
    --cron "0 8 * * *" \
    --tz "Australia/Sydney" \
    --session isolated \
    --message "<agent prompt for full pipeline>" \
    --announce \
    --channel <user_channel> \
    --to "<user_target>"
  ```
- [ ] Write agent prompt that covers: check schedule → download PDF → extract text → generate thread → announce for approval
- [ ] Document the browser fallback flow: agent detects 403 from Python CLI → uses `browser` tool to navigate ParlInfo → downloads PDF → saves to `data/pdfs/`
- [ ] Test cron job fires and agent completes pipeline end-to-end (manual verification)
- [ ] Document approval flow: user receives announce → replies with approval → agent publishes

Phase 6: Robustness + polish
- [ ] Add structured logging throughout pipeline
- [ ] Rate limiting for ParlInfo requests (respect retry-after headers)
- [ ] PDF size/validity checks before extraction
- [ ] PDF retention policy (configurable max age/count)
- [ ] Graceful handling of schedule page changes (new URL patterns, table structure changes)
- [ ] Error reporting: agent announces failures with actionable detail (which step failed, what to do)

Tests summary
- [x] 18 existing tests (all passing): schedule parsing, ordering, ref_no sort, PDF link extraction, committee fallback, 403 handling, storage, downloader, CLI download-latest
- [ ] Phase 2 tests: MarkItDown extraction, summariser prompt/output validation
- [ ] Phase 3 tests: pending store CRUD, approval state machine
- [ ] Phase 4 tests: X client mock, thread creation, partial failure resume
- [ ] Manual E2E: cron job → schedule check → download → extract → summarise → approve → publish

Dev notes
- Python 3.13.7 venv at `.venv/`
- Dependencies: `requests`, `beautifulsoup4`, `pytest` (installed). To add: `markitdown`, `openai`/HTTP, `tweepy`/HTTP.
- No `playwright` dependency in Python — browser automation is at the OpenClaw layer.
- All JSON output from CLI commands for agent consumption.
