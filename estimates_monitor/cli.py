"""CLI entrypoint for one-pass processing"""
import argparse
from estimates_monitor import downloader, parser, summarizer, storage, schedule
from pathlib import Path
import json
from datetime import datetime
import sys


def process_entry(entry, openai_call_func):
    # entry: dict with keys page_url, title, pdf_url, published_date
    id_ = entry.get("page_url")
    if storage.is_seen(id_):
        return None
    pdf_url = entry.get("pdf_url")
    pdf_path = None
    if pdf_url:
        pdf_path = downloader.download_pdf(pdf_url, filename_hint=entry.get("title"))
    else:
        raise RuntimeError("No pdf_url for entry")
    text = parser.extract_text_with_markitdown(pdf_path)
    thread = summarizer.summarise_pipeline(text, entry.get("title"), pdf_url, openai_call_func)
    # save draft
    draft_dir = Path("data/drafts")
    draft_dir.mkdir(parents=True, exist_ok=True)
    out_path = draft_dir / (Path(id_).name.replace("/","_") + ".json")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"id": id_, "title": entry.get("title"), "pdf_url": pdf_url, "thread": thread}, f, indent=2, ensure_ascii=False)
    storage.mark_seen(id_, {"title": entry.get("title"), "pdf_url": pdf_url})
    return str(out_path)


def main(openai_call_func):
    # For MVP we operate from fixtures: load fixtures/schedule_entries.json if present
    fixture = Path("fixtures/schedule_entries.json")
    if fixture.exists():
        entries = json.loads(fixture.read_text(encoding="utf-8"))
    else:
        raise RuntimeError("No fixtures provided for MVP. Live scraping not implemented in MVP CLI.")
    results = []
    for e in entries:
        r = process_entry(e, openai_call_func)
        if r:
            results.append(r)
    return results


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
        "pdf_fallback_committee": entry.pdf_fallback_committee,
    })
    return {
        "id": entry.page_url,
        "title": entry.title,
        "pdf_url": entry.pdf_url,
        "published_date": published,
        "status": entry.status,
        "pdf_fallback_committee": entry.pdf_fallback_committee,
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
        "pdf_fallback_committee": entry.pdf_fallback_committee,
    }


def run_resolve_pdf(display_url, session=None):
    # Fetch given parlInfo display URL and extract pdf_url without mutating state
    # Try requests first, fall back to browser-based fetcher when blocked.
    import requests
    from estimates_monitor.parlinfo import extract_pdf_url
    try:
        s = session or requests
        resp = s.get(display_url)
        if getattr(resp, 'status_code', None) == 403:
            raise requests.exceptions.HTTPError(response=resp)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        # Try browser-based fetcher
        from estimates_monitor.fetcher import fetch_html
        html = fetch_html(display_url, session=session)
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
    try:
        entry = schedule.get_latest_published(session=session, is_seen_func=_is_downloaded, timeout_s=timeout_s)
    except TypeError:
        # Back-compat for tests/mocks that stub get_latest_published without the new timeout_s kwarg.
        entry = schedule.get_latest_published(session=session, is_seen_func=_is_downloaded)
    if not entry:
        _v("no entry")
        return None

    _v(f"selected ref_no={getattr(entry, 'ref_no', None)} title={entry.title!r}")

    if storage.is_posted(entry.page_url):
        _v("refusing: already posted")
        raise SystemExit(2)
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
            "pdf_fallback_committee": entry.pdf_fallback_committee,
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
        playwright_referer_url=entry.page_url,
        verbose=verbose,
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
    dl_parser.add_argument("--timeout", type=int, default=60, help="Timeout seconds for network/browser operations")
    dl_parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    resolve = sub.add_parser("resolve-pdf", help="Resolve a ParlInfo display URL to its PDF without mutating state")
    resolve.add_argument("display_url")
    setup = sub.add_parser("parlinfo-setup", help="Open headed browser to allow interactive ParlInfo WAF pass and save profile")
    setup.add_argument("display_url")
    parser_arg.add_argument("--run", action="store_true")
    args = parser_arg.parse_args()
    # Provide a naive openai_call_func for manual runs that echoes prompts (developer replaces with real client)
    def echo_call(prompt):
        return {"mock": True, "prompt_sample": prompt[:100]}
    if args.command == "latest":
        if getattr(args, 'absolute', False):
            result = run_latest_absolute()
        else:
            result = run_latest()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "download-latest":
        # Watchdog: if something hangs (requests/playwright), dump a traceback.
        timeout_s = getattr(args, 'timeout', 60)
        verbose = getattr(args, 'verbose', False)
        try:
            import faulthandler
            faulthandler.enable()
            # Give a small grace period beyond the user timeout.
            faulthandler.dump_traceback_later(timeout_s + 20, repeat=False)
        except Exception:
            faulthandler = None

        try:
            result = run_download_latest(
                force_download=args.force_download,
                dry_run=getattr(args, 'dry_run', False),
                timeout_s=timeout_s,
                verbose=verbose,
            )
        finally:
            try:
                if faulthandler:
                    faulthandler.cancel_dump_traceback_later()
            except Exception:
                pass

        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "resolve-pdf":
        url = args.display_url
        pdf = run_resolve_pdf(url)
        print(json.dumps({"display_url": url, "pdf_url": pdf}, indent=2, ensure_ascii=False))
    elif args.command == "parlinfo-setup":
        # Open headed browser once for user to interactively pass WAF; uses same profile dir as fetcher.
        url = args.display_url
        from estimates_monitor.fetcher import _browser_fetch_with_playwright
        profile = "data/playwright-profile"
        print("Opening headed browser. Please interact with the page and complete any challenge. Close the browser when done.")
        try:
            _browser_fetch_with_playwright(url, user_data_dir=profile, prefer_headed=True)
            print(f"Profile saved to {profile}")
        except Exception as exc:
            print(f"Setup failed: {exc}")
    elif args.run:
        print("Running CLI against fixtures...")
        out = main(echo_call)
        print("Outputs:", out)
