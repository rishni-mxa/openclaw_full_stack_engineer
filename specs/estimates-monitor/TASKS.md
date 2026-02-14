TASKS.md - Implementation tasks (Spec Kit Lite) — updated for approval-gate + X API publish + ParlInfo Path A

Priority 1 (MVP)
- [ ] Create specs (SPEC.md, PLAN.md, TASKS.md, UAT.md) (this set)
- [ ] Create Python package skeleton (estimates_monitor) with modules: downloader, parser, summarizer, storage, cli, x_client
- [ ] Implement state.json read/write helpers (storage.py)
- [ ] Implement schedule parser that accepts HTML (parser.parse_schedule(html)) and returns list of entries with: page_url, title, published_date, pdf_url (optional), status_text
- [ ] Implement downloader that given a pdf_url saves file to data/pdfs and returns path
- [ ] Implement parser wrapper that uses markitdown to extract text (parser.extract_text(pdf_path)) — allow injection/mocking of markitdown for tests
- [ ] Implement summarizer that calls OpenAI (summarizer.summarize(text)) with chunking and returns thread JSON
- [ ] Implement pending thread store: save generated threads to data/pending/<thread_id>.json with status metadata
- [ ] CLI entrypoint commands: plan (generate thread + save pending), approve <id> (publish via x_client or dry-run), status (show pending/published)
- [ ] Implement mockable x_client.py with create_post(text, reply_to_id=None) which can be swapped for a real X API client later
- [ ] Unit tests + fixtures (schedule HTML, small PDF or text fixture)
- [ ] Add parlinfo-setup command with clear interactive instructions: how to run, what to expect from the WAF, and where the profile is saved (data/playwright-profile/). Acceptance gate: operator can confirm post-setup that the target ParlInfo URL loads in the headed browser and the setup exits with success.

Priority 2 (Robustness)
- [ ] Implement browser fallback to extract PDF URL if schedule page is JS-driven
- [ ] Implement PDF retention policy and size checks
- [ ] Add logging and retry/backoff for network calls
- [ ] Implement resume logic for partially published threads and idempotency handling
- [ ] Add detection for WAF challenge (Azure WAF markers) and retry logic: on HTTP 403 or challenge markers, try Playwright headless using persisted profile; if that fails, surface an error requiring parlinfo-setup.
- [ ] Enforce safety: single-page fetch only, rate limiting (default 1 request per 10s), and limit concurrent Playwright sessions to 1 for ParlInfo.

Priority 3 (Optional enhancements)
- [ ] Real web integration tests (recorded HTTP fixtures)
- [ ] Dockerfile and CI config with tests
- [ ] Integrate with main agent notifications (via provided interface)

Tests and verification
- [ ] Offline deterministic tests: unit tests for schedule parsing, PDF parsing (using local PDF fixtures), summariser logic (mock OpenAI), and x_client mock tests.
- [ ] Manual verification checklist: parlinfo-setup run, confirm profile saved, fetch_html fallback triggers Playwright correctly, and retry flow requires re-setup when appropriate.

Documentation
- [ ] Update README and CLI help to document parlinfo-setup, profile storage location and permissions, WAF detection behavior, and operator instructions for re-running setup.

Dev notes
- Keep dependencies small: requests, beautifulsoup4, markitdown, playwright, openai (or HTTP to OpenAI), pytest
- Design modules for testability: allow injection of HTTP client, OpenAI client, Playwright browser launcher, and X client

Acceptance gates
- parlinfo-setup present and documented with clear operator instructions; operator can run locally and confirm success.
- WAF detection implemented and tested in mocks; fallback to Playwright using persisted profile implemented.
- Tests: offline unit tests pass and manual verification checklist included in UAT.

Constraints / Safety
- Do NOT implement live OAuth token exchange or persist real credentials without the main agent confirming X developer credentials are available and acceptable to use.
- Publishing must only occur after explicit approve <thread_id> action by an operator or main agent.
