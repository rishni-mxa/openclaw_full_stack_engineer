UAT.md — Acceptance tests and checklist (updated 2026-02-15)

Architecture note: There is NO Playwright in the Python library. Browser-based WAF bypass
is handled entirely by the OpenClaw agent via its `browser` tool. The Python library uses
`requests` only and raises on 403. The daily pipeline runs as an OpenClaw cron job.

---

Preconditions
- Python 3.13+ venv at `.venv/` with `requests`, `beautifulsoup4`, `pytest` installed
- `markitdown` installed for PDF text extraction
- OpenClaw agent configured with managed `openclaw` Chrome profile
- OpenClaw cron job configured (daily 8am AEST, isolated session, announce to user channel)
- For real publish testing: X developer credentials as env vars (`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`)

---

## 1. Unit tests (automated)

- [ ] `pytest` — all tests pass (currently 18, target 25+ after Phases 2–4)
- [ ] No test touches the network or requires credentials

## 2. Schedule detection (Phase 1 — DONE)

CLI commands run from project root via `python -m estimates_monitor.cli`.

### 2a. Latest transcript lookup
```
python -m estimates_monitor.cli latest --absolute
```
- [ ] Returns JSON with `page_url`, `title`, `status_text` = "Published in full", `ref_no`
- [ ] `ref_no` is the highest among all "Published in full" entries

### 2b. PDF URL resolution
```
python -m estimates_monitor.cli resolve-pdf <parlinfo_detail_url>
```
- [ ] Returns the exact `toc_pdf` URL (not the inline viewer URL)
- [ ] If ParlInfo returns 403 (WAF), the command raises an error — this is expected; the agent handles the 403 via browser tool

### 2c. PDF download
```
python -m estimates_monitor.cli download-latest
```
- [ ] Downloads PDF to `data/pdfs/<content_hash>.pdf`
- [ ] `state.json` updated with `seen` entry for the transcript
- [ ] Re-running with same schedule skips download (idempotent)
- [ ] `--dry-run` prints what would be downloaded without fetching
- [ ] `--force-download` re-downloads even if already seen

### 2d. Committee page fallback
- [ ] If APH schedule page returns 403, the system falls back to the committee page URL
- [ ] If committee fallback also fails, raises with clear error message

## 3. Text extraction (Phase 2)

### 3a. MarkItDown extraction
- [ ] `parser.extract_text_with_markitdown(pdf_path)` returns non-empty text string
- [ ] Text preserves paragraph structure from Senate Estimates transcript
- [ ] Senator names, committee names, and department references are intact

## 4. Summarisation (Phase 2)

### 4a. Thread generation
- [ ] `summarizer.summarise_pipeline(text, llm_call)` with mock LLM returns valid JSON:
  ```json
  {"tweets": [{"text": "..."}], "notes": "..."}
  ```
- [ ] Each tweet text ≤ 280 characters
- [ ] Thread length ≤ 8 tweets
- [ ] Content is coherent summary of Australian Senate Estimates proceedings

## 5. Pending thread store + approval gate (Phase 3)

### 5a. Thread saved to pending store
- [ ] After summarisation, thread saved to `data/pending/<thread_id>.json`
- [ ] JSON contains: `thread_id`, `transcript_id`, `title`, `pdf_url`, `tweets[]`, `status` = "pending", `created_at`

### 5b. Status command
```
python -m estimates_monitor.cli status
```
- [ ] Lists all pending and published threads with IDs and statuses

### 5c. Approve (dry-run)
```
python -m estimates_monitor.cli approve <thread_id> --dry-run
```
- [ ] Prints exact per-tweet payloads (text, reply_to order) without any API calls
- [ ] No state changes occur

### 5d. Reject
```
python -m estimates_monitor.cli reject <thread_id>
```
- [ ] Marks thread as rejected; thread is not publishable

## 6. X API publishing (Phase 4)

### 6a. Approve (real)
```
python -m estimates_monitor.cli approve <thread_id>
```
- [ ] Root tweet posted, reply chain threaded correctly via `reply_to_id`
- [ ] Each published post ID recorded in pending store
- [ ] `state.json` updated via `mark_posted()`
- [ ] Thread status transitions: pending → approved → published

### 6b. Partial failure + resume
- [ ] If post N of M fails, thread status = "failed", last successful post ID recorded
- [ ] Re-running `approve <thread_id>` resumes from post N+1
- [ ] Already-posted tweets are NOT re-posted (idempotent)

### 6c. Idempotency
- [ ] `approve` on an already-published thread does nothing

## 7. OpenClaw cron job (Phase 5)

### 7a. Daily automated run
- [ ] Cron fires at 8am AEST daily
- [ ] Agent executes full pipeline: schedule check → detect new transcript → download PDF → extract text → generate thread → save to pending → announce for approval
- [ ] If no new transcript, agent announces "No new transcripts" and exits

### 7b. WAF bypass
- [ ] When Python CLI raises 403 on ParlInfo, agent uses `browser` tool to navigate ParlInfo in managed `openclaw` profile
- [ ] Agent extracts PDF URL from the loaded page and downloads the PDF
- [ ] Agent saves PDF to `data/pdfs/` and continues pipeline

### 7c. Approval flow
- [ ] Agent announces pending thread (title, tweet preview, thread_id) to user channel
- [ ] User replies with approval (or rejection)
- [ ] Agent runs `approve <thread_id>` to publish, or `reject <thread_id>` to discard
- [ ] Agent announces publish result (success with URLs, or failure with error detail)

### 7d. Error handling
- [ ] On any pipeline failure, agent announces the error with: which step failed, the error message, and suggested remediation
- [ ] Cron retry policy: exponential backoff (configured at cron level)

---

## Definition of Done

- All `pytest` tests pass
- CLI commands `latest`, `download-latest`, `resolve-pdf`, `status`, `approve --dry-run` work locally
- Cron job configured and verified to fire (manual trigger test)
- At least one real end-to-end run: schedule → PDF → text → thread → approve (dry-run) completed successfully
- Real X publish tested with approval gate before first live post

## Notes for reviewer

- No Playwright in the Python library — all browser automation is at the OpenClaw agent layer
- Publishing requires explicit operator approval; no automated posting without human-in-the-loop
- X credentials must be env vars, never committed to repo
- Tests must not require network access or real credentials — mock all external services
