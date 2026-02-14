"""Playwright PDF downloader (subprocess helper).

This module is invoked as a subprocess to ensure we can hard-timeout and kill
browser work if it hangs.

Usage:
  python -m estimates_monitor.pw_download --url <pdf_url> --profile <dir> --out <file> [--referer <url>] [--timeout-ms 60000] [--verbose]

Writes the response body to --out and prints a one-line JSON result to stdout.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional
import sys
import time


def _strip_fragment(url: str) -> str:
    return url.split("#", 1)[0]


def _log(msg: str, verbose: bool):
    if verbose:
        print(msg, file=sys.stdout, flush=True)


def download_pdf_to_file(
    url: str,
    profile_dir: Path,
    out_path: Path,
    referer_url: Optional[str] = None,
    timeout_ms: int = 60000,
    verbose: bool = False,
    dump_links: bool = False,
) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return {
            "ok": False,
            "error": "playwright_not_installed",
            "detail": str(e),
        }

    profile_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    url = _strip_fragment(url)
    referer_url = _strip_fragment(referer_url) if referer_url else None

    # Absolute wall-clock watchdog inside the subprocess.
    start = time.time()

    _log(f"[pw_download] start url={url}", verbose)
    if referer_url:
        _log(f"[pw_download] referer={referer_url}", verbose)
    _log(f"[pw_download] profile_dir={profile_dir}", verbose)

    with sync_playwright() as p:
        _log("[pw_download] launching persistent context", verbose)
        # NOTE: ParlInfo is serving a WAF block page to headless automation.
        # Use headed mode with the persisted profile to behave like a normal browser.
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
        )
        try:
            default_headers = {
                "Referer": referer_url or "https://parlinfo.aph.gov.au/",
                "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
            }

            def _request_bytes(u: str) -> tuple[int, bytes, str]:
                """Fetch bytes via Playwright's APIRequestContext.

                This avoids Chromium's built-in PDF viewer, which can cause `page.goto()` to
                return an HTML viewer document instead of the raw PDF bytes.
                """
                r = context.request.get(u, headers=default_headers)
                ct = r.headers.get("content-type", "") if getattr(r, "headers", None) else ""
                return r.status, r.body(), ct

            page = context.new_page()
            page.set_extra_http_headers(default_headers)


            _log(f"[pw_download] goto (timeout_ms={timeout_ms}): {url}", verbose)
            resp = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            if resp is None:
                return {"ok": False, "error": "no_response"}

            status = resp.status
            _log(f"[pw_download] status: {status}", verbose)

            # Wall-clock check
            if (time.time() - start) * 1000 > timeout_ms:
                return {"ok": False, "error": "timeout", "detail": "wall_clock_exceeded"}

            if status >= 400:
                # Try click-through from referer page if provided.
                if referer_url:
                    _log("[pw_download] attempting click-through via referer page", verbose)
                    page2 = context.new_page()
                    page2.goto(referer_url, wait_until="networkidle", timeout=timeout_ms)

                    if dump_links:
                        try:
                            title = page2.title()
                        except Exception as ex:
                            title = f"<title_failed: {ex}>"
                        try:
                            inner = page2.evaluate("() => document.body ? (document.body.innerText || '') : ''")
                            inner_snip = (inner or "")[:400]
                        except Exception as ex:
                            inner_snip = f"<innerText_failed: {ex}>"
                        try:
                            a_count = page2.locator('a').count()
                        except Exception as ex:
                            a_count = f"<count_failed: {ex}>"

                        # Dump candidate links for diagnostics (hrefs containing parlinfo/download or toc_pdf)
                        js = """
                        () => Array.from(document.querySelectorAll('a[href]'))
                          .map(a => a.getAttribute('href'))
                          .filter(h => h && (h.includes('parlInfo/download') || h.includes('/parlInfo/download') || h.includes('toc_pdf')))
                        """
                        try:
                            hrefs = page2.evaluate(js)
                        except Exception as ex:
                            hrefs = [f"<evaluate_failed: {ex}>" ]
                        print(json.dumps({
                            "kind": "referer_diag",
                            "title": title,
                            "final_url": page2.url,
                            "anchor_count": a_count,
                            "text_snippet": inner_snip,
                            "download_like_count": len(hrefs),
                            "download_like_hrefs": hrefs[:200],
                        }, ensure_ascii=False), flush=True)

                    target = url

                    def _is_target(r):
                        try:
                            return _strip_fragment(r.url) == target
                        except Exception:
                            return False

                    # The DOM often uses relative hrefs like "/parlInfo/download/...".
                    from urllib.parse import urlsplit
                    parts = urlsplit(target)
                    rel = parts.path + (f"?{parts.query}" if parts.query else "")
                    rel_dir = rel.rsplit("/", 1)[0] + "/"

                    try:
                        with page2.expect_response(_is_target, timeout=timeout_ms) as resp_info:
                            # Prefer clicking a clear "Download PDF" link if present.
                            loc = page2.locator("a", has_text="Download PDF")
                            if loc.count() > 0:
                                loc.first.click(timeout=timeout_ms)
                            else:
                                # Fallback: click any anchor whose href starts with the relative download path.
                                page2.click(f"a[href^='{rel_dir}']", timeout=timeout_ms)
                        r = resp_info.value
                        _log(f"[pw_download] click-response status: {r.status}", verbose)
                        if r.status >= 400:
                            return {"ok": False, "error": "http_error", "status": r.status}
                        # Fetch via request context to avoid PDF viewer / HTML wrapper.
                        st, data, ct = _request_bytes(_strip_fragment(r.url))
                        _log(f"[pw_download] request.get status: {st} content-type: {ct}", verbose)
                        if st >= 400:
                            return {"ok": False, "error": "http_error", "status": st}
                    except Exception as e:
                        return {"ok": False, "error": "click_download_failed", "detail": str(e)}
                else:
                    return {"ok": False, "error": "http_error", "status": status}
            else:
                # Even if navigation works, fetch bytes via request context to avoid PDF viewer.
                st, data, ct = _request_bytes(url)
                _log(f"[pw_download] request.get status: {st} content-type: {ct}", verbose)
                if st >= 400:
                    return {"ok": False, "error": "http_error", "status": st}

            if not data.startswith(b"%PDF"):
                # Helpful diagnostic: we likely received an HTML interstitial.
                head = data[:200].decode("utf-8", errors="replace")
                return {"ok": False, "error": "not_a_pdf", "bytes": len(data), "head": head}

            _log(f"[pw_download] writing bytes={len(data)} to {out_path}", verbose)
            out_path.write_bytes(data)
            return {"ok": True, "bytes": len(data), "path": str(out_path)}
        finally:
            try:
                context.close()
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--referer")
    ap.add_argument("--timeout-ms", type=int, default=60000)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--dump-links",
        action="store_true",
        help="When referer is provided, dump candidate download links found on the referer page (diagnostics).",
    )
    args = ap.parse_args()

    result = download_pdf_to_file(
        url=args.url,
        profile_dir=Path(args.profile),
        out_path=Path(args.out),
        referer_url=args.referer,
        timeout_ms=args.timeout_ms,
        verbose=args.verbose,
        dump_links=args.dump_links,
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
