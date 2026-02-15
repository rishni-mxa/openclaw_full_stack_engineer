"""CLI entrypoint for estimates-monitor commands."""
import argparse
from estimates_monitor import downloader, storage, schedule
from pathlib import Path
import json
from datetime import datetime
import sys


def run_latest(session=None, now_func=None):
    # Prefer first not-seen entry according to schedule ordering.
    entry = schedule.get_latest_published(session=session, is_seen_func=storage.is_seen)
    if not entry:
        return None
    now = (now_func or datetime.utcnow)().isoformat() + "Z"
    published = entry.published_date.isoformat() if entry.published_date else None
    storage.mark_seen(entry.page_url, {
        "first_seen_at": now,
        "title": entry.title,
        "pdf_url": entry.pdf_url,
        "published_date": published,
        "status": entry.status,
    })
    return {
        "id": entry.page_url,
        "title": entry.title,
        "pdf_url": entry.pdf_url,
        "published_date": published,
        "status": entry.status,
    }


def run_latest_absolute(session=None):
    # Ignore seen/downloaded state and return the highest ref_no Published full entry
    entry = schedule.get_latest_published(session=session, is_seen_func=lambda _id: False)
    if not entry:
        return None
    published = entry.published_date.isoformat() if entry.published_date else None
    return {
        "id": entry.page_url,
        "title": entry.title,
        "pdf_url": entry.pdf_url,
        "published_date": published,
        "status": entry.status,
    }


def run_resolve_pdf(display_url, session=None):
    """Fetch given parlInfo display URL and extract pdf_url without mutating state.

    Uses requests only. Raises on 403 (WAF) — browser bypass is handled by
    the OpenClaw agent.
    """
    import requests
    from estimates_monitor.parlinfo import extract_pdf_url
    s = session or requests
    resp = s.get(display_url)
    resp.raise_for_status()
    html = resp.text
    pdf = extract_pdf_url(display_url, html)
    return pdf


def _base_name_from_entry(entry):
    if entry.published_date:
        return entry.published_date.date().isoformat()
    return entry.title or "transcript"


def run_download_latest(session=None, now_func=None, force_download: bool = False, dry_run: bool = False, timeout_s: int = 60, verbose: bool = False):
    def _v(msg: str):
        if verbose:
            print(f"[download-latest] {msg}", file=sys.stdout, flush=True)

    _v(f"start timeout_s={timeout_s} force_download={force_download} dry_run={dry_run}")

    # Prefer first not-seen entry according to schedule ordering.
    # For downloads we treat 'seen' (discovery) separately from 'downloaded'.
    # Pass an is_seen_func that returns True only when an entry has already been downloaded
    # (i.e., storage.get_seen(id) exists and has a non-empty pdf_path). This lets us prefer
    # entries that were seen but not yet downloaded.
    def _is_downloaded(id_):
        s = storage.get_seen(id_)
        return bool(s and s.get("pdf_path"))

    _v("fetching schedule + selecting latest published")
    entry = schedule.get_latest_published(session=session, is_seen_func=_is_downloaded, timeout_s=timeout_s)
    if not entry:
        _v("no entry")
        return None

    _v(f"selected ref_no={getattr(entry, 'ref_no', None)} title={entry.title!r}")

    if storage.is_posted(entry.page_url):
        _v("refusing: already posted")
        raise SystemExit(2)
    if not entry.pdf_url and getattr(entry, 'parlinfo_blocked', False):
        _v("ParlInfo blocked by WAF — browser bypass needed")
        published = entry.published_date.isoformat() if entry.published_date else None
        return {
            "id": entry.page_url,
            "title": entry.title,
            "pdf_url": None,
            "published_date": published,
            "status": entry.status,
            "parlinfo_blocked": True,
            "parlinfo_url": entry.page_url,
            "action": "browser_fetch",
            "instructions": (
                "ParlInfo returned 403 (WAF). Use browser tool to: "
                f"1) Open {entry.page_url} "
                "2) Find the PDF link containing '/toc_pdf/' "
                "3) Download that PDF to data/pdfs/"
            ),
        }
    if not entry.pdf_url:
        raise RuntimeError("No pdf_url for latest entry")

    _v(f"resolved pdf_url={entry.pdf_url}")

    # If dry_run requested, return resolved metadata without downloading or mutating state
    if dry_run:
        published = entry.published_date.isoformat() if entry.published_date else None
        return {
            "id": entry.page_url,
            "title": entry.title,
            "pdf_url": entry.pdf_url,
            "published_date": published,
            "status": entry.status,
            "skipped": False,
        }

    existing = storage.get_seen(entry.page_url)
    if existing and existing.get("pdf_path") and not force_download:
        _v("skipping: already downloaded")
        return {
            "id": entry.page_url,
            "title": entry.title,
            "pdf_url": entry.pdf_url,
            "pdf_path": existing.get("pdf_path"),
            "pdf_sha256": existing.get("pdf_sha256"),
            "pdf_bytes": existing.get("pdf_bytes"),
            "skipped": True,
        }

    base_name = _base_name_from_entry(entry)
    _v(f"downloading pdf base_name={base_name!r}")
    dl = downloader.download_pdf_deterministic(
        entry.pdf_url,
        base_name,
        session=session,
        timeout=timeout_s,
    )
    _v(f"downloaded bytes={dl.get('bytes')} sha256={dl.get('sha256')}")
    now = (now_func or datetime.utcnow)().isoformat() + "Z"
    published = entry.published_date.isoformat() if entry.published_date else None
    storage.update_seen(entry.page_url, {
        "first_seen_at": existing.get("first_seen_at") if existing else now,
        "title": entry.title,
        "pdf_url": entry.pdf_url,
        "published_date": published,
        "status": entry.status,
        "downloaded_at": now,
        "pdf_path": dl["path"],
        "pdf_sha256": dl["sha256"],
        "pdf_bytes": dl["bytes"],
    })
    return {
        "id": entry.page_url,
        "title": entry.title,
        "pdf_url": entry.pdf_url,
        "pdf_path": dl["path"],
        "pdf_sha256": dl["sha256"],
        "pdf_bytes": dl["bytes"],
        "skipped": False,
    }


if __name__ == "__main__":
    parser_arg = argparse.ArgumentParser()
    sub = parser_arg.add_subparsers(dest="command")
    latest_parser = sub.add_parser("latest", help="Fetch latest published schedule entry and mark seen")
    latest_parser.add_argument("--absolute", action="store_true", dest="absolute", help="Ignore seen state and return absolute latest")
    dl_parser = sub.add_parser("download-latest", help="Download latest published transcript PDF")
    dl_parser.add_argument("--force-download", action="store_true")
    dl_parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    dl_parser.add_argument("--timeout", type=int, default=60, help="Timeout seconds for network operations")
    dl_parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    resolve = sub.add_parser("resolve-pdf", help="Resolve a ParlInfo display URL to its PDF without mutating state")
    resolve.add_argument("display_url")
    args = parser_arg.parse_args()
    if args.command == "latest":
        if getattr(args, 'absolute', False):
            result = run_latest_absolute()
        else:
            result = run_latest()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "download-latest":
        timeout_s = getattr(args, 'timeout', 60)
        verbose = getattr(args, 'verbose', False)
        result = run_download_latest(
            force_download=args.force_download,
            dry_run=getattr(args, 'dry_run', False),
            timeout_s=timeout_s,
            verbose=verbose,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "resolve-pdf":
        url = args.display_url
        pdf = run_resolve_pdf(url)
        print(json.dumps({"display_url": url, "pdf_url": pdf}, indent=2, ensure_ascii=False))
