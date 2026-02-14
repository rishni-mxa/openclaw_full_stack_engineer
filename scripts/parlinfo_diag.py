from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DISPLAY_URL = "http://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id%3A%22committees%2Festimate%2F29366%2F0002%22"
PROFILE_DIR = Path("data/playwright-profile")
OUT_DIR = Path("data/diag")

KEYWORDS = [
    "download/committees/estimate/29366",
    "parlInfo/download",
    "toc_pdf",
    "29366",
]


def main():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []

    def want(url: str) -> bool:
        u = url.lower()
        return any(k.lower() in u for k in KEYWORDS)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
        )
        page = context.new_page()

        def on_request(req):
            url = req.url
            if want(url):
                events.append({"kind": "request", "url": url, "method": req.method})

        def on_response(resp):
            url = resp.url
            if want(url):
                try:
                    status = resp.status
                except Exception:
                    status = None
                events.append({"kind": "response", "url": url, "status": status})

        page.on("request", on_request)
        page.on("response", on_response)

        # Navigate
        page.goto(DISPLAY_URL, wait_until="domcontentloaded", timeout=60000)
        # Give scripts time to run
        time.sleep(5)
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        time.sleep(3)

        # Capture artifacts
        title = page.title()
        url_now = page.url
        html = page.content()
        OUT_DIR.joinpath("parlinfo_29366.html").write_text(html, encoding="utf-8")
        page.screenshot(path=str(OUT_DIR / "parlinfo_29366.png"), full_page=True)

        # Text snippet
        inner_text = page.evaluate("() => document.body ? document.body.innerText : ''")
        snippet = (inner_text or "")[:800]

        # Candidate clickable elements
        js = r"""
        () => {
          const kws = ['pdf','download','toc','parlinfo'];
          const nodes = Array.from(document.querySelectorAll('a,button,[role=button]'));
          const out = [];
          for (const el of nodes) {
            const text = (el.innerText || el.textContent || '').trim();
            const href = el.getAttribute && el.getAttribute('href');
            const onclick = el.getAttribute && el.getAttribute('onclick');
            const aria = el.getAttribute && el.getAttribute('aria-label');
            const hay = (text + ' ' + (href||'') + ' ' + (aria||'') + ' ' + (onclick||'')).toLowerCase();
            if (!hay) continue;
            if (kws.some(k => hay.includes(k))) {
              out.push({
                tag: el.tagName,
                text: text.slice(0,200),
                href,
                aria,
                onclick,
                role: el.getAttribute && el.getAttribute('role'),
              });
            }
          }
          return out.slice(0, 300);
        }
        """
        clickables = page.evaluate(js)

        report = {
            "display_url": DISPLAY_URL,
            "final_url": url_now,
            "title": title,
            "text_snippet": snippet,
            "keyword_events": events,
            "clickables": clickables,
            "artifacts": {
                "html": str(OUT_DIR / "parlinfo_29366.html"),
                "screenshot": str(OUT_DIR / "parlinfo_29366.png"),
            },
        }
        OUT_DIR.joinpath("parlinfo_29366_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        print(json.dumps({"ok": True, "report": str(OUT_DIR / "parlinfo_29366_report.json")}, ensure_ascii=False))

        # Keep window for a moment so operator can see it, then close.
        time.sleep(2)
        context.close()


if __name__ == "__main__":
    main()
