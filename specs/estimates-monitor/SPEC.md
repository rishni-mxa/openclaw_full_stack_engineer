Feature: APH Senate Estimates transcript monitor -> X thread generation + approval-publish flow

Goal
- Detect newly "Published in full" transcripts from APH Estimates Transcript Schedule and produce X (formerly Twitter) threads summarising each transcript for Rish to review and approve before publishing.

High-level flow
1. Scrape the schedule page for transcript entries marked "Published in full".
2. For each new entry (not recorded in state.json), fetch its detail page and download the PDF transcript.
3. Extract text from the PDF using markitdown (or an injected extractor for testability).
4. Summarize the transcript into a top-down X thread using OpenAI (gpt-5-mini).
5. Save the generated thread to a pending store under data/pending/<thread_id>.json and notify the main agent for human approval.
6. On explicit approval from the main agent, publish the thread via the X API as real posts (thread created by posting a root post then replying to build the thread). Update pending state to published and record published IDs in state.json.

ParlInfo WAF (Path A) — new requirement
- ParlInfo (parlinfo.aph.gov.au) is protected by an Azure WAF that may present an interactive challenge when first accessed from a new browser profile or environment. The system MUST support a one-time interactive unlock step performed by a human operator to establish a persistent browser profile that can be used by automated runs.
- This is a required precondition for automation: automated fetching of ParlInfo pages is only expected to succeed after the one-time setup completes successfully.

Scenarios
- First-run setup (interactive): Operator runs parlinfo-setup <url>. This launches a headed browser (Playwright persistent context) using a profile directory (e.g. data/playwright-profile/). The operator completes the WAF/interactive challenge (if shown), verifies access to the given ParlInfo page, then exits the browser. The profile directory is persisted for use by automated fetches.
- Steady-state automated runs: Automated processes run headless and use the persisted Playwright profile to fetch ParlInfo pages. Normal fetching is by HTTP requests; on 403/blocked responses the system falls back to Playwright using the persisted profile. If the profile no longer satisfies the WAF (e.g. cookies expired or cleared), operators must re-run parlinfo-setup to refresh the profile.

Non-goals
- Automatic posting without an explicit approval step.
- Attempting to circumvent WAF protections or to automate bypass of interactive challenge without human oversight.

Outputs
- Updated SPEC.md, PLAN.md, TASKS.md, UAT.md reflecting approval-gate -> publish workflow and Path A WAF setup
- Minimal Python package with modules: downloader, parser, summarizer, storage (state), x_client (API client), cli entrypoint
- state.json to track seen transcripts and published post IDs
- Pending thread storage under data/pending/
- Unit tests for thread splitting & approval flow state transitions

Constraints & choices (summary)
- Stable IDs: Use canonical transcript page URLs + generated thread_id (UUID) as primary keys.
- PDF downloads: HTTP requests preferred; Playwright fallback using persisted profile when WAF blocks direct requests.
- markitdown: use Python API where practical; allow injection/mocking for tests.
- OpenAI: chunked summarisation (map-reduce) with clear prompt templates and an output JSON schema for threads.
- Publishing: Prefer X API (OAuth2 user context) to create real posts on approval. If X developer credentials are not available, the system will keep threads in pending state and require the main agent to provide publishing credentials or perform the publish step manually.
- Safety: Explicit approval gate enforced; publishing only occurs after explicit approve <thread_id> CLI command from an operator or main agent invocation.
