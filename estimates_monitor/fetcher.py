"""Fetch HTML pages via requests.

Browser-based WAF bypass (for ParlInfo's Azure WAF JS Challenge) is handled by
the OpenClaw agent's browser tool, not this module.  This module provides a
simple requests-only fetch with WAF detection helpers so callers can decide
whether to escalate to a browser.
"""

import requests
from estimates_monitor.schedule import DEFAULT_HEADERS
from typing import Optional


def _is_azure_waf_content(html: str, url: str) -> bool:
    """Return True if the response looks like an Azure WAF JS Challenge page."""
    if not html:
        return True
    if 'Azure WAF' in html or '/.azwaf/' in url or '/.azwaf/' in html:
        return True
    return False


def fetch_html(url: str, session: Optional[requests.Session] = None) -> str:
    """Fetch HTML for a single page using requests.

    Raises requests.HTTPError on non-success status codes (including 403 WAF blocks).
    Callers that need browser-based WAF bypass should catch the 403 and delegate
    to the OpenClaw browser tool.
    """
    s = session or requests
    resp = s.get(url, headers=DEFAULT_HEADERS)
    resp.raise_for_status()
    return resp.text

