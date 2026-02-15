#!/usr/bin/env python3
"""Agent workflow: fetch the latest Senate Estimates transcript PDF.

Usage (tell the OpenClaw agent):
    Run `python scripts/fetch_transcript.py` and follow any instructions in the output.

This script handles everything it can via HTTP requests. When ParlInfo blocks
with a WAF 403, it outputs a structured JSON result with action="browser_fetch"
telling the agent exactly what to do with its browser tool.

Exit codes:
    0 — PDF downloaded successfully (or browser instructions emitted)
    1 — error
    2 — already posted, nothing to do
"""

import sys, json, os
from pathlib import Path

# Ensure package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from estimates_monitor import schedule, downloader, storage
from datetime import datetime


def main():
    # Step 1: Find latest published transcript
    print(">>> Step 1: Checking schedule for latest published transcript...", flush=True)

    try:
        entry = schedule.get_latest_published(
            is_seen_func=lambda id_: bool(
                (s := storage.get_seen(id_)) and s.get("pdf_path")
            ),
            timeout_s=30,
        )
    except Exception as e:
        _fail(f"Failed to fetch schedule: {e}")

    if entry is None:
        _fail("No published transcripts found on schedule page.")

    print(f"    Found: ref={entry.ref_no} title={entry.title!r}", flush=True)
    print(f"    ParlInfo URL: {entry.page_url}", flush=True)

    # Step 2: Check if already posted
    if storage.is_posted(entry.page_url):
        result = {
            "status": "already_posted",
            "id": entry.page_url,
            "title": entry.title,
        }
        print(f"\n>>> Already posted. Nothing to do.", flush=True)
        print(f"\n===RESULT===\n{json.dumps(result, indent=2)}")
        sys.exit(2)

    # Step 3: Handle ParlInfo WAF block
    if getattr(entry, 'parlinfo_blocked', False) or not entry.pdf_url:
        if getattr(entry, 'parlinfo_blocked', False):
            print(f"\n>>> Step 2: ParlInfo returned 403 (WAF challenge).", flush=True)
            print(f"    Browser bypass required.", flush=True)

            result = {
                "status": "browser_required",
                "action": "browser_fetch",
                "id": entry.page_url,
                "title": entry.title,
                "ref_no": entry.ref_no,
                "parlinfo_url": entry.page_url,
                "save_dir": "data/pdfs",
                "instructions": [
                    f"Open this URL in your browser: {entry.page_url}",
                    "Wait for the page to fully load (WAF challenge will resolve automatically).",
                    "Find the PDF download link — look for a link containing '/toc_pdf/' in the href.",
                    "Download that PDF file.",
                    f"Save it to the data/pdfs/ directory.",
                    "Then run: python scripts/fetch_transcript.py --register-pdf <path_to_downloaded_pdf>",
                ],
            }
            print(f"\n===RESULT===\n{json.dumps(result, indent=2)}")
            sys.exit(0)
        else:
            _fail(f"No PDF URL resolved and ParlInfo not blocked — unexpected state.")

    # Step 4: Download PDF via requests
    print(f"\n>>> Step 2: Downloading PDF...", flush=True)
    print(f"    URL: {entry.pdf_url}", flush=True)

    base_name = entry.published_date.date().isoformat() if entry.published_date else (entry.title or "transcript")

    try:
        dl = downloader.download_pdf_deterministic(
            entry.pdf_url,
            base_name,
            timeout=60,
        )
    except Exception as e:
        _fail(f"PDF download failed: {e}")

    print(f"    Saved: {dl['path']} ({dl['bytes']} bytes, sha256={dl['sha256'][:16]}...)", flush=True)

    # Step 5: Record in state
    now = datetime.utcnow().isoformat() + "Z"
    published = entry.published_date.isoformat() if entry.published_date else None
    storage.update_seen(entry.page_url, {
        "first_seen_at": now,
        "title": entry.title,
        "pdf_url": entry.pdf_url,
        "published_date": published,
        "status": entry.status,
        "downloaded_at": now,
        "pdf_path": dl["path"],
        "pdf_sha256": dl["sha256"],
        "pdf_bytes": dl["bytes"],
    })

    result = {
        "status": "downloaded",
        "id": entry.page_url,
        "title": entry.title,
        "ref_no": entry.ref_no,
        "pdf_url": entry.pdf_url,
        "pdf_path": dl["path"],
        "pdf_sha256": dl["sha256"],
        "pdf_bytes": dl["bytes"],
    }
    print(f"\n>>> Done. PDF downloaded successfully.", flush=True)
    print(f"\n===RESULT===\n{json.dumps(result, indent=2)}")
    sys.exit(0)


def register_pdf():
    """Register a manually-downloaded PDF against the latest entry in state."""
    pdf_path = sys.argv[sys.argv.index("--register-pdf") + 1]
    if not Path(pdf_path).exists():
        _fail(f"PDF not found: {pdf_path}")

    import hashlib
    hasher = hashlib.sha256()
    data = Path(pdf_path).read_bytes()
    hasher.update(data)
    sha = hasher.hexdigest()
    size = len(data)

    # Get latest entry from schedule (ignore seen state)
    entry = schedule.get_latest_published(
        is_seen_func=lambda _: False,
        timeout_s=30,
    )
    if entry is None:
        _fail("No published transcripts found.")

    now = datetime.utcnow().isoformat() + "Z"
    published = entry.published_date.isoformat() if entry.published_date else None
    storage.update_seen(entry.page_url, {
        "first_seen_at": now,
        "title": entry.title,
        "pdf_url": entry.page_url,  # ParlInfo URL as reference
        "published_date": published,
        "status": entry.status,
        "downloaded_at": now,
        "pdf_path": pdf_path,
        "pdf_sha256": sha,
        "pdf_bytes": size,
    })

    result = {
        "status": "registered",
        "id": entry.page_url,
        "title": entry.title,
        "ref_no": entry.ref_no,
        "pdf_path": pdf_path,
        "pdf_sha256": sha,
        "pdf_bytes": size,
    }
    print(f">>> PDF registered: {pdf_path} ({size} bytes)", flush=True)
    print(f"\n===RESULT===\n{json.dumps(result, indent=2)}")


def _fail(msg):
    print(f">>> ERROR: {msg}", file=sys.stderr, flush=True)
    result = {"status": "error", "error": msg}
    print(f"\n===RESULT===\n{json.dumps(result, indent=2)}")
    sys.exit(1)


if __name__ == "__main__":
    if "--register-pdf" in sys.argv:
        register_pdf()
    else:
        main()
