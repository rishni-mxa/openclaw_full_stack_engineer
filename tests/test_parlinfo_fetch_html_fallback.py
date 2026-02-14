"""Test that a 403 from ParlInfo falls back to the committee page for PDF resolution.

Browser-based WAF bypass is now handled by the OpenClaw agent, not by the
schedule module.  On 403, schedule.get_latest_published goes directly to the
committee page if available.
"""

from estimates_monitor import schedule
from types import SimpleNamespace


def test_403_triggers_committee_fallback():
    """When ParlInfo returns 403, schedule should fall back to the committee page."""
    schedule_html = '''
    <html><body><table><tbody>
      <tr>
        <td>10/02/2026</td>
        <td><a href="/committee/rra">Rural and Regional Affairs</a></td>
        <td>29366</td>
        <td><a href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22">Published in full</a></td>
      </tr>
    </tbody></table></body></html>
    '''

    parlinfo_display_url = "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22"
    committee_url = "https://example.org/committee/rra"

    class DummyResp(SimpleNamespace):
        def raise_for_status(self):
            if getattr(self, 'status_code', 200) >= 400:
                import requests
                exc = requests.exceptions.HTTPError(str(self.status_code))
                exc.response = self
                raise exc

    class DummySession:
        def __init__(self, mapping):
            self.mapping = mapping
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append(url)
            return self.mapping[url]

    committee_html = '<html><body><a href="/-/media/Estimates/rrat/add2526/RRAT.pdf">Download</a></body></html>'

    sess = DummySession({
        "https://example.org": DummyResp(url="https://example.org", text=schedule_html, status_code=200),
        parlinfo_display_url: DummyResp(url=parlinfo_display_url, text="", status_code=403),
        committee_url: DummyResp(url=committee_url, text=committee_html, status_code=200),
    })

    orig = schedule.SCHEDULE_URL_CANDIDATES
    schedule.SCHEDULE_URL_CANDIDATES = ["https://example.org"]
    try:
        latest = schedule.get_latest_published(session=sess)
    finally:
        schedule.SCHEDULE_URL_CANDIDATES = orig

    assert latest is not None
    assert latest.pdf_fallback_committee is True
    assert latest.pdf_url is not None
    assert '/-/media/' in latest.pdf_url or 'aph.gov.au' in latest.pdf_url
