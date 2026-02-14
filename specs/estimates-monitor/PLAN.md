Plan: Implementation approach and decisions (updated for approval-gate + X API publish + ParlInfo Path A WAF)

Additions / Key decisions

ParlInfo WAF: Path A (one-time human-assisted unlock)
- parlinfo-setup command: CLI command parlinfo-setup <url> launches a headed Playwright persistent context using a profile directory persisted under data/playwright-profile/ (configurable path). The command should:
  - Open the provided ParlInfo URL in a headed browser using Playwright's persistent context.
  - Allow the operator to complete any WAF/interactive challenge presented by the Azure WAF.
  - Confirm access (HTTP 200 and expected page content) before exiting.
  - Persist the profile directory contents (cookies, localStorage, etc.) to data/playwright-profile/ with restricted permissions.
- The setup is explicitly one-time (or occasional) and requires human interaction. The system must clearly instruct the operator about what to do and warn that profile data is sensitive and should be stored with appropriate filesystem permissions.

fetch_html strategy with WAF fallback
- Preferred path: perform a plain HTTP GET request for target ParlInfo pages (requests). If response is HTTP 200 and contains expected content, continue.
- On HTTP 403 or evidence of WAF challenge (see detection below), attempt to fetch using Playwright with the persisted profile in headless mode.
- If Playwright fetch using the persisted profile still encounters an active interactive challenge or returns non-200, surface an explicit error and require re-running parlinfo-setup (headed) to refresh the profile.
- Playwright use should be single-page fetches only (no crawling of site), and must run with navigation timeouts and resource limits to avoid long-running sessions.

WAF detection
- Detect WAF protections by HTTP status codes (403), common Azure WAF headers or challenge page markers (e.g., known HTML snippets, JS challenge text, or anti-bot meta tags). Make markers configurable and conservative to avoid false positives.

Safety and crawl limits
- The system must avoid aggressive crawling of ParlInfo. Use single-page fetch logic: only fetch the exact URL required to resolve the PDF or detail page.
- Enforce rate limits: default 1 request per 10 seconds to ParlInfo domain (configurable). Respect retry-after headers when present.
- Limit concurrent Playwright sessions to 1 for ParlInfo fetching to avoid triggering additional WAF scrutiny.

Data handling and profile storage
- Profile directory: data/playwright-profile/ (default). Store only what's necessary: cookies, localStorage, and any Playwright profile artifacts needed to maintain session authentication.
- Permissions: the profile directory must be created with restrictive filesystem permissions (owner read/write only) and documented in PLAN and TASKS.
- Do not commit profile data to version control. Add data/playwright-profile/ to .gitignore.

Failure modes and recovery
- Common failures:
  - Initial HTTP 403: fallback to Playwright using persisted profile if available; otherwise require parlinfo-setup.
  - Playwright still blocked (challenge persists): instruct operator to re-run parlinfo-setup (headed) to re-authenticate and refresh profile.
  - Expired cookies or cleared profile: detect and require re-setup.
  - Network errors/timeouts: retry with exponential backoff (configurable attempts) for transient issues.
- Recovery steps should be explicit in logs and CLI outputs: tell operator when to re-run parlinfo-setup, when a profile is missing/corrupt, and provide clear exit codes for automation.

Security notes
- Treat profile data as sensitive. Document storage location and required filesystem permissions. Recommend operators store backups securely if desired but avoid cloud-syncing the profile directory.

Integration with existing plan items
- When fetching PDFs or detail pages for transcripts, use the fetch_html strategy above. The rest of the plan (X publishing, summariser, pending store) remains unchanged.

Other sections (X API publishing model, Idempotency, Failure recovery, Validation, Security, Operational notes, Data model, CLI commands, Testing and mocks, Observability)
- Remain as previously documented. See earlier sections for X publishing decisions and constraints.
