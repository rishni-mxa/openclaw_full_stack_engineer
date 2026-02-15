#!/usr/bin/env python3
"""Diagnostic script: traces the full download-latest pipeline and writes
a detailed report to data/diagnose.md so you can share it for debugging."""

import sys, os, json, textwrap
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, unquote

# Ensure package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from estimates_monitor import schedule, parlinfo, storage
from bs4 import BeautifulSoup
import requests

REPORT_PATH = Path("data/diagnose.md")
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

lines = []  # accumulate report lines

def log(text=""):
    lines.append(text)

def log_heading(level, text):
    log(f"\n{'#' * level} {text}\n")

def log_code(text, lang=""):
    log(f"```{lang}")
    log(text.rstrip())
    log("```")

def log_kv(key, value):
    log(f"- **{key}:** `{value}`")


def main():
    log_heading(1, "Estimates Monitor — Download Diagnostic")
    log(f"**Run at:** {datetime.now().isoformat()}")
    log(f"**Python:** {sys.version}")
    log()

    # ── Step 1: Fetch schedule page ──────────────────────────────────
    log_heading(2, "Step 1 — Fetch schedule page")
    for url in schedule.SCHEDULE_URL_CANDIDATES:
        log_kv("Candidate URL", url)

    try:
        resp = schedule._fetch_schedule(timeout_s=30)
        log_kv("Final URL (after redirects)", resp.url)
        log_kv("Status code", resp.status_code)
        log_kv("Content-Length", len(resp.text))
    except Exception as e:
        log(f"\n**ERROR fetching schedule:** `{e}`")
        _write_report()
        return

    # ── Step 2: Parse schedule HTML ──────────────────────────────────
    log_heading(2, "Step 2 — Parse schedule entries")
    base_url = getattr(resp, "url", None) or schedule.SCHEDULE_URL
    entries = schedule._parse_schedule_html(resp.text, base_url=base_url)
    log_kv("Total entries parsed", len(entries))
    log()

    if not entries:
        log("**No entries found.** The schedule HTML may have changed structure.")
        log("\nFirst 2000 chars of HTML body:")
        log_code(resp.text[:2000], "html")
        _write_report()
        return

    # Show all entries
    log("| # | Ref No | Title | Status | Date | page_url (truncated) | committee_url? |")
    log("|---|--------|-------|--------|------|----------------------|----------------|")
    for i, e in enumerate(entries):
        ref = e.ref_no or "—"
        dt = e.published_date.strftime("%Y-%m-%d") if e.published_date else "—"
        purl = e.page_url[:80] + ("…" if len(e.page_url) > 80 else "")
        curl = "yes" if e.committee_url else "no"
        log(f"| {i+1} | {ref} | {e.title[:40]} | {e.status} | {dt} | {purl} | {curl} |")
    log()

    # ── Step 3: Sort + select ────────────────────────────────────────
    log_heading(2, "Step 3 — Sort and select latest")
    entries.sort(key=schedule._sort_key_latest, reverse=True)

    # Check seen state
    for i, e in enumerate(entries[:5]):
        seen = storage.get_seen(e.page_url)
        downloaded = bool(seen and seen.get("pdf_path"))
        log(f"- Entry {i+1}: ref={e.ref_no} seen={bool(seen)} downloaded={downloaded} → `{e.page_url[:80]}`")

    # Select using same logic as CLI
    def _is_downloaded(id_):
        s = storage.get_seen(id_)
        return bool(s and s.get("pdf_path"))

    chosen = None
    for e in entries:
        if not _is_downloaded(e.page_url):
            chosen = e
            break
    if chosen is None:
        chosen = entries[0]

    log()
    log_kv("Selected entry title", chosen.title)
    log_kv("Selected ref_no", chosen.ref_no)
    log_kv("Selected page_url", chosen.page_url)
    log_kv("Selected committee_url", chosen.committee_url or "(none)")
    log_kv("Selected status", chosen.status)
    log_kv("Selected date", chosen.published_date)
    log()

    # ── Step 4: Resolve PDF URL ──────────────────────────────────────
    log_heading(2, "Step 4 — Resolve PDF URL from detail page")

    detail_html = None
    detail_base = chosen.page_url
    parlinfo_403 = False
    committee_fallback = False

    # 4a: Try the ParlInfo detail page
    log_heading(3, "4a — Fetch ParlInfo detail page")
    log_kv("URL", chosen.page_url)
    try:
        detail_resp = requests.get(chosen.page_url, headers=schedule.DEFAULT_HEADERS, timeout=30)
        log_kv("Status", detail_resp.status_code)
        log_kv("Final URL", detail_resp.url)
        log_kv("Content-Length", len(detail_resp.text))

        if detail_resp.status_code == 403:
            parlinfo_403 = True
            log("\n**Got 403 from ParlInfo (WAF challenge)**")
            # Show first 500 chars of body for WAF diagnosis
            log("\nFirst 500 chars of 403 response:")
            log_code(detail_resp.text[:500], "html")
        else:
            detail_resp.raise_for_status()
            detail_html = detail_resp.text
            detail_base = detail_resp.url
    except requests.HTTPError as e:
        resp_obj = getattr(e, 'response', None)
        status = getattr(resp_obj, 'status_code', None)
        log_kv("HTTP Error status", status)
        if status == 403:
            parlinfo_403 = True
            log("\n**Got 403 from ParlInfo (WAF challenge)**")
        else:
            log(f"\n**Non-403 HTTP Error:** `{e}`")
    except Exception as e:
        log(f"\n**Unexpected error:** `{type(e).__name__}: {e}`")

    # 4b: Committee page fallback
    if parlinfo_403 and chosen.committee_url:
        committee_fallback = True
        log_heading(3, "4b — Fallback: fetch committee page")
        log_kv("Committee URL", chosen.committee_url)
        try:
            fb_resp = requests.get(chosen.committee_url, headers=schedule.DEFAULT_HEADERS, timeout=30)
            log_kv("Status", fb_resp.status_code)
            log_kv("Final URL", fb_resp.url)
            log_kv("Content-Length", len(fb_resp.text))
            fb_resp.raise_for_status()
            detail_html = fb_resp.text
            detail_base = fb_resp.url
        except Exception as e:
            log(f"\n**Committee page also failed:** `{e}`")

    if detail_html is None:
        log("\n**No detail HTML available — cannot resolve PDF URL.**")
        _write_report()
        return

    # ── Step 5: Scan for PDF links ───────────────────────────────────
    log_heading(2, "Step 5 — All PDF links found in detail HTML")

    soup = BeautifulSoup(detail_html, "html.parser")
    all_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_lower = href.lower()
        if ".pdf" in href_lower or "application%2fpdf" in href_lower or "application/pdf" in href_lower:
            full_url = requests.compat.urljoin(detail_base, href)
            link_text = a.get_text(" ", strip=True)[:60]
            all_links.append({"text": link_text, "href": href[:120], "resolved": full_url})

    log_kv("Total PDF links found", len(all_links))
    log()
    if all_links:
        log("| # | Link text | href (raw, truncated) | Resolved URL |")
        log("|---|-----------|----------------------|--------------|")
        for i, lk in enumerate(all_links):
            log(f"| {i+1} | {lk['text']} | `{lk['href']}` | `{lk['resolved'][:100]}` |")
    else:
        log("**No PDF links found at all!**")
        log("\nFirst 3000 chars of detail HTML:")
        log_code(detail_html[:3000], "html")
    log()

    # ── Step 6: ParlInfo extractor result ────────────────────────────
    log_heading(2, "Step 6 — ParlInfo extractor result (parlinfo.extract_pdf_url)")
    parsed_page = urlparse(chosen.page_url)
    hostname = (parsed_page.hostname or "").lower()

    if "parlinfo.aph.gov.au" in hostname and not committee_fallback:
        pdf_from_parlinfo = parlinfo.extract_pdf_url(chosen.page_url, detail_html)
        log_kv("parlinfo.extract_pdf_url result", pdf_from_parlinfo or "(None)")
    else:
        log(f"Skipped — page host is `{hostname}`, committee_fallback={committee_fallback}")
        pdf_from_parlinfo = None

    # ── Step 7: _pick_pdf_link result ────────────────────────────────
    log_heading(2, "Step 7 — Generic _pick_pdf_link result")
    est_id, doc_id, id_str = schedule._extract_estimate_id_parts(chosen.page_url)
    log_kv("estimate_id", est_id or "(None)")
    log_kv("doc_id", doc_id or "(None)")
    log_kv("id_str", id_str or "(None)")
    log_kv("detail_base used for resolution", detail_base)

    pdf_generic = schedule._pick_pdf_link(detail_html, detail_base, estimate_id=est_id, id_str=id_str)
    log_kv("_pick_pdf_link result", pdf_generic or "(None)")

    # ── Step 8: Final chosen PDF URL ─────────────────────────────────
    log_heading(2, "Step 8 — Final PDF URL selection")
    final_pdf = None
    if pdf_from_parlinfo:
        final_pdf = pdf_from_parlinfo
        log_kv("Source", "parlinfo.extract_pdf_url")
    elif pdf_generic:
        final_pdf = pdf_generic
        log_kv("Source", "_pick_pdf_link (generic)")
    else:
        log("**No PDF URL could be resolved!**")

    # Committee fallback host rewrite check
    if committee_fallback and final_pdf:
        parsed_pdf = urlparse(final_pdf)
        if parsed_pdf.path.startswith("/-/media/"):
            rewritten = parsed_pdf._replace(scheme="https", netloc="www.aph.gov.au")
            log_kv("Host rewrite applied", f"{parsed_pdf.netloc} → www.aph.gov.au")
            final_pdf = rewritten.geturl()

    log_kv("**Final PDF URL**", final_pdf or "(None)")

    # ── Step 9: Diagnosis ────────────────────────────────────────────
    log_heading(2, "Step 9 — Diagnosis")

    expected_url_fragment = "parlinfo"
    if final_pdf and "/-/media/" in final_pdf:
        log("⚠️ **The selected PDF is a direct APH media file** (e.g. committee opening statement or program PDF).")
        log("This is likely NOT the full transcript. The transcript PDF lives on ParlInfo.")
        log()
        log("**Root cause:** ParlInfo returned 403 (WAF), so the code fell back to the committee page,")
        log("which has its own PDFs (program, opening statements, etc.) — not the transcript.")
        log()
        log("**Fix:** The OpenClaw agent needs to use its `browser` tool to bypass the ParlInfo WAF,")
        log("navigate to the ParlInfo detail page, and extract the correct `toc_pdf` link.")
    elif final_pdf and "parlinfo" in final_pdf.lower():
        log("✅ PDF URL points to ParlInfo — this looks correct.")
    elif final_pdf:
        log(f"⚠️ PDF URL does not contain 'parlinfo' — verify this is the right transcript: `{final_pdf}`")
    else:
        log("❌ No PDF URL resolved.")

    if parlinfo_403:
        log()
        log("**ParlInfo 403 detected.** The agent should:")
        log("1. Use `browser` tool to open the ParlInfo detail URL")
        log(f"2. URL: `{chosen.page_url}`")
        log("3. Find the PDF link containing `/toc_pdf/`")
        log("4. Download that PDF and save to `data/pdfs/`")

    _write_report()


def _write_report():
    report = "\n".join(lines)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Diagnostic report written to: {REPORT_PATH.resolve()}")
    print(f"({len(lines)} lines)")


if __name__ == "__main__":
    main()
