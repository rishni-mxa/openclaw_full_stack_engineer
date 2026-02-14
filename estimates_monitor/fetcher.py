import requests
from estimates_monitor.schedule import DEFAULT_HEADERS
from typing import Optional
from pathlib import Path
import time
import sys

# Note: avoid importing OpenClaw browser tooling at module import time (causes ModuleNotFoundError in tests).
# Implement an optional Playwright-based fallback invoked at runtime when requests returns 403.


def _is_azure_waf_content(html: str, url: str) -> bool:
    if not html:
        return True
    if 'Azure WAF' in html or '/.azwaf/' in url or '/.azwaf/' in html:
        return True
    return False


def _browser_fetch_with_playwright(url: str, user_data_dir: Optional[str] = None, prefer_headed: bool = False) -> str:
    """Fetch page HTML using Playwright.

    IMPORTANT: Playwright persistent profiles are created via `launch_persistent_context`,
    not `launch(user_data_dir=...)`.

    - If `user_data_dir` is provided, we use a persistent context so cookies/tokens persist.
    - We try headless first unless `prefer_headed=True`.
    - If the content looks like an Azure WAF challenge, callers may retry headed.

    Returns: `page.content()`.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise RuntimeError(
            "Playwright is required for browser fallback. Install it with: `pip install playwright` "
            "and then run: `playwright install chromium`"
        )

    profile_dir = Path(user_data_dir) if user_data_dir else None

    def _open_page(p, headed: bool):
        ua = DEFAULT_HEADERS.get("User-Agent")
        extra_headers = {k: v for k, v in DEFAULT_HEADERS.items() if k.lower() != "user-agent"}

        if profile_dir:
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=not headed,
                user_agent=ua,
            )
            # Extra headers can be set per page
            page = context.new_page()
            page.set_extra_http_headers(extra_headers)
            return context, None, page

        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(user_agent=ua)
        page = context.new_page()
        page.set_extra_http_headers(extra_headers)
        return context, browser, page

    try:
        with sync_playwright() as p:
            context, browser, page = _open_page(p, headed=prefer_headed)
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                url_now = page.url
                passed = not _is_azure_waf_content(html, url_now)

                # If looks like WAF challenge and we started headless, retry headed and poll.
                if not passed and not prefer_headed:
                    try:
                        context.close()
                    except Exception:
                        pass
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass

                    context, browser, page = _open_page(p, headed=True)
                    page.goto(url, wait_until="networkidle", timeout=0)

                    start = time.time()
                    timeout_s = 120
                    while time.time() - start < timeout_s:
                        time.sleep(1)
                        url_now = page.url
                        html = page.content()
                        if not _is_azure_waf_content(html, url_now):
                            passed = True
                            break

                print(f"Playwright final URL: {url_now}", file=sys.stdout)
                print(f"Azure WAF challenge passed: {passed}", file=sys.stdout)
                return html
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
    except Exception as exc:
        raise RuntimeError(f"Playwright browser fetch failed: {exc}")


def fetch_html(url: str, session: Optional[requests.Session] = None) -> str:
    """Fetch HTML for a single page. Try requests first with sensible headers; if the response is
    an explicit 403 (bot-block) attempt to retrieve the page with a browser automation fallback.

    This function is intentionally small and synchronous and returns the page HTML as text.
    Tests should mock this function when controlling network behaviour.
    """
    s = session or requests
    try:
        resp = s.get(url, headers=DEFAULT_HEADERS)
        # If successful, return the HTML even if redirected
        if getattr(resp, 'status_code', None) and resp.status_code < 400:
            return resp.text
        # If 403, fall through to browser fallback
        if getattr(resp, 'status_code', None) != 403:
            resp.raise_for_status()
    except Exception:
        # If the exception contains a response with 403 status, continue to browser fallback
        pass

    # Playwright fallback. ParlInfo serves WAF block pages to headless automation,
    # so we go headed by default when we have to fall back to the browser.
    profile = Path('data/playwright-profile')
    profile.mkdir(parents=True, exist_ok=True)
    try:
        html = _browser_fetch_with_playwright(url, user_data_dir=str(profile), prefer_headed=True)
        return html
    except RuntimeError:
        # Bubble up previous informative RuntimeError
        raise
