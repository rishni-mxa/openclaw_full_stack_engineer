UAT.md - Acceptance tests and checklist (updated for approval-publish flow + ParlInfo Path A)

Preconditions
- Developer has Python 3.10+ and pip
- Optional: markitdown available (pip install markitdown)
- Playwright installed for parlinfo-setup (pip install playwright) and browsers installed (playwright install)
- If testing real publish: X developer credentials and operator OAuth tokens must be provided by the main agent (do not store in repo).

Checklist (MVP)
- [ ] Run CLI plan against provided fixtures and confirm:
  - [ ] state.json created and populated with seen transcript id(s)
  - [ ] PDF downloaded to data/pdfs/
  - [ ] Text extracted to data/text/ (or used in-memory)
  - [ ] Pending thread JSONs created under data/pending/ with fields: thread_id, id, title, pdf_url, tweets[], status=pending
- [ ] Unit tests pass (pytest)
- [ ] Integration test (fixture): end-to-end run completes without hitting external web

ParlInfo Path A: interactive setup and steady-state checks
- First-run interactive setup (parlinfo-setup)
  - [ ] Run: parlinfo-setup <parlinfo-url>
  - [ ] Headed Playwright opens; operator completes any WAF challenge presented by Azure WAF.
  - [ ] Operator confirms the page loads and the command exits successfully.
  - [ ] Profile saved to data/playwright-profile/ with restrictive filesystem permissions.
  - Acceptance gate: operator verifies the target ParlInfo URL loads in the headed browser and parlinfo-setup exits with success.

- Steady-state automated fetch
  - [ ] Run automated fetch (resolve-pdf <parlinfo-detail-url> or download-latest) in an environment that uses the persisted profile.
  - [ ] If initial HTTP request is 200, proceed. If HTTP 403 or WAF markers detected, the system uses Playwright with the persisted profile to fetch the page.
  - [ ] If Playwright headless fetch succeeds, the pipeline continues and resolves the exact toc_pdf URL.
  - [ ] If Playwright still shows a challenge or returns non-200, operator must re-run parlinfo-setup (headed) to refresh the profile.

UAT steps for Rish (explicit)
1) Run parlinfo-setup <url>
   - Confirm the headed browser opens, WAF challenge (if any) is completed, and the command exits with success.
2) Run resolve-pdf <29366 url>
   - Confirm the command returns the exact toc_pdf URL (the PDF link used by the pipeline) and exits with success.
3) Run download-latest
   - Confirm the latest PDF referenced by the schedule is downloaded to data/pdfs/ and that the file is the expected PDF.

Approval & publish flow
- [ ] Use CLI status to list pending threads
- [ ] Use CLI approve <thread_id> --dry-run to simulate publishing and show per-post payloads; confirm no external calls were made
- [ ] After main agent/operator confirmation, run CLI approve <thread_id> (real mode) to publish via X API. Confirm:
  - [ ] API responses returned post IDs for each posted tweet
  - [ ] data/pending/<thread_id>.json updated status to published and includes published post IDs
  - [ ] state.json updated with published post IDs and thread metadata

Failure and resume
- [ ] Simulate a mid-thread failure in tests (mock x_client to fail on Nth post). Confirm: thread status is failed, highest published post recorded, and CLI approve can resume publishing remaining posts.

Dry-run mode
- [ ] Dry-run produces the exact per-post payloads and order that would be sent to the X API, including normalized URL handling and idempotency keys, without sending HTTP requests.

Definition of Done (updated)
- Engineer must run the parlinfo-setup and local UAT steps (resolve-pdf and download-latest) successfully on their machine before requesting review. The PR description must include confirmation that these steps were run and any profile-related notes.

Notes for reviewer
- Publishing requires explicit operator approval. If X developer credentials are not available during UAT, the approve command should be restricted to --dry-run only and real publish attempts should be blocked until the main agent supplies credentials.
- The tests must not include real credentials. Mock the X client for unit tests.
