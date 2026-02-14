# APH Senate Estimates → Transcript PDF → X thread (handoff)

Date: 2026-02-13/14 (Sydney)

This doc summarises what we intended to build, what we tried, what failed (and why), what we learned, and the path forward. Use it to finish the build with Chris.

---

## 1) What we intended to build (end-to-end)

**Goal:** Monitor the APH *Senate Estimates Transcript Schedule* for new transcripts marked **“Published in full”**, download the transcript PDF, extract text, summarise into a top-down **X (Twitter) thread**, save as a **pending draft**, and **only publish after explicit human approval**.

**Pipeline (target):**
1. Fetch schedule page.
2. Parse rows; select the latest “Published in full” transcript (primary sort by **Ref No. descending**; date only as fallback).
3. Follow transcript link (typically a ParlInfo display URL).
4. Resolve the *actual transcript PDF URL* (prefer `toc_pdf`).
5. Download PDF bytes deterministically to `data/pdfs/` and record hash/size.
6. Extract text (MarkItDown).
7. Summarise into an X thread (gpt-5-mini).
8. Save under `data/pending/<thread_id>.json`.
9. Publish only when a human explicitly runs `approve <thread_id>`.

---

## 2) What we built so far (workspace-engineer)

Implemented modules/commands (highlights):
- **Schedule parsing**: `estimates_monitor/schedule.py`
  - Correctly uses the **Transcript column** link ("Published in full") as the canonical `page_url`.
  - Sort by Ref No (numeric) descending; date fallback.
- **State**: `estimates_monitor/storage.py`
  - Tracks `seen` vs `posted`, plus download metadata (`pdf_path`, `pdf_sha256`, `pdf_bytes`, timestamps).
- **ParlInfo PDF URL extraction**: `estimates_monitor/parlinfo.py`
  - Extracts a PDF URL from ParlInfo display HTML; strongly prefers `/toc_pdf/`.
- **Fetch abstraction**: `estimates_monitor/fetcher.py`
  - `requests` first, Playwright fallback when blocked.
- **Downloader**: `estimates_monitor/downloader.py`
  - `download_pdf_deterministic()` with requests-first and Playwright subprocess fallback on 403.
- **Playwright subprocess helper**: `estimates_monitor/pw_download.py`
  - The critical WAF/PDF handling work lives here.
- **CLI**: `estimates_monitor/cli.py`
  - `latest`, `latest --absolute`
  - `resolve-pdf <display_url>`
  - `parlinfo-setup <display_url>` (interactive WAF pass)
  - `download-latest [--dry-run] [--force-download] [--timeout] [--verbose]`

Tests exist (offline + mocked integration) and were kept green during iteration.

---

## 3) What failed and why

### A) ParlInfo / Azure WAF blocks headless automation
Symptoms:
- Direct requests to ParlInfo PDF endpoints return **403**.
- Playwright **headless** loading the referer display page returns a **WAF block page** (title: “Parlinfo WAF Block Page”), meaning no download link exists in the DOM to click.

Conclusion:
- ParlInfo WAF distinguishes headless automation and blocks it.

### B) “HTTP 200” didn’t mean “we got a PDF”
When we switched to **headed** Playwright, `page.goto(pdf_url)` returned 200, but the bytes we wrote were **HTML** (Chromium PDF viewer / interstitial), not `%PDF`.

Fix:
- Fetch bytes using Playwright’s **APIRequestContext**:
  - `context.request.get(url, headers=...)`
  - Verify `content-type: application/pdf` and bytes start with `%PDF`.

### C) APH schedule page instability (502 / timeouts)
During the last runs, `download-latest` appeared to “hang” but the root cause was APH returning:
- **502 Bad Gateway** and/or
- **ReadTimeout**

Fix:
- Ensure hard timeouts and add watchdog/tracebacks so this fails fast and debugs cleanly.

---

## 4) What we learned (important)

1) **Spec process:** “Spec Kit Lite” needs an explicit **Research / Recon phase before planning**.
   - If we had reconned ParlInfo early, we would have planned for headed automation from day 1 (or chosen a different data source).

2) **WAF reality:** Some sites will allow the HTML display page but block binary downloads (or block headless entirely). Treat access as a first-class risk.

3) **PDF downloading with Playwright:**
   - `page.goto()` is not a reliable way to obtain PDF bytes (PDF viewer).
   - Use `context.request.get()` (or `page.request.get()` in non-persistent contexts) and validate `%PDF`.

4) **Observability beats guessing:** Adding DOM/network diagnostics (title, innerText snippet, link dumps) immediately explained why click-based download failed.

---

## 5) Path forward (recommended)

### Step 1 — Accept headed Playwright for ParlInfo steps
Given the WAF behaviour observed, use **headed Playwright** for:
- fetching ParlInfo display HTML when requests gets 403
- downloading the transcript PDF bytes

Everything else can remain non-interactive.

### Step 2 — Make `download-latest` robust
- Keep strict timeouts on schedule fetch.
- Add retry/backoff for schedule fetch (within a deadline).
- Keep the faulthandler watchdog (stack trace on hangs).

### Step 3 — Finish the “Transcript → X thread” capability
- Add MarkItDown extraction (already planned).
- Add summariser (gpt-5-mini) that outputs a structured thread.
- Add pending store + explicit approval gate.
- Only after approval: publish via X API.

### Step 4 — Operational runbook
- Operator does **one-time** `parlinfo-setup <display_url>` to refresh profile when needed.
- Automated runs should clearly error if profile is missing/expired.

---

## 6) Practical notes / commands

**Key acceptance checks:**
- `resolve-pdf <display_url>` returns a `toc_pdf` URL for the correct estimate id.
- Playwright download writes a real PDF (`%PDF` bytes).

**Representative URLs (example we debugged):**
- Display: `...display.w3p;query=Id:"committees/estimate/29366/0002"`
- PDF: `.../parlInfo/download/committees/estimate/29366/toc_pdf/...pdf;fileType=application%2Fpdf`

---

## 7) Change request to Spec Kit Lite
Add a mandatory section at the top of PLAN:
- **0) Research / recon** (15–60 minutes)
  - validate access (WAF/bot protection)
  - verify download endpoints return real bytes
  - capture a minimal diagnostic artifact (HTML snippet + screenshot if needed)

(Implemented in `workspace-engineer/templates/PLAN.template.md`.)
